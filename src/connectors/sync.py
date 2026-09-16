"""Complete snapshots, isolated adapter workers, atomic local publication."""
import hashlib,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from src.config import ROOT
from src.database import db
from src.auth import validate_metadata
from src.logging_setup import event,now
from src.file_safety import read_regular
from src.connectors.base import canonical,project,ConfigurationError,IncompleteSnapshot,ConnectorError
from src.connectors.registry import resolve,create_adapter,fingerprint,load_catalog

def row_metadata(dataset,row):
    meta=dict(dataset['metadata'])
    mapping=dataset.get('row_acl',{})
    actor_keys={'owner_field','allowed_users_field','allowed_roles_field'}
    if actor_keys & set(mapping):
        # Dataset policy is checked separately. Per-record grants must restrict it,
        # never inherit a broad dataset role that overrides row-level restrictions.
        meta['allowed_users']=[];meta['allowed_roles']=[]
    for key,field in mapping.items():
        value=row.get(field)
        if value is None: raise ConnectorError('Missing row ACL value; refusing snapshot')
        target={'owner_field':'owner','allowed_users_field':'allowed_users','allowed_roles_field':'allowed_roles','classification_field':'classification'}[key]
        if target=='classification':
            if type(value) is not int: raise ConnectorError('Row classification must be integer')
            value=max(value,meta['classification'])
        meta[target]=value
    if 'owner_field' in mapping and not {'allowed_users_field','allowed_roles_field'} & set(mapping):
        meta['allowed_users']=[meta['owner']]
    return validate_metadata(meta)

def sync_dataset(dataset_id,period=None,isolated=True):
    source,dataset=resolve(dataset_id)
    scope=period or '' if dataset.get('sync_scope','all')=='period' else ''
    if dataset.get('sync_scope','all')=='period':
        from src.analytics import validate_period
        validate_period(period)
    run_id=str(uuid.uuid4());start=time.monotonic()
    with db.connect() as conn:
        db.execute(conn,'INSERT INTO eail_sync_runs VALUES (?,?,?,?,?,?,?)',(run_id,dataset_id,scope,'running',now(),'',''))
    try:
        if isolated:
            with tempfile.TemporaryDirectory(prefix='eail-source-') as tmp:
                output=Path(tmp)/'snapshot.json'
                process=subprocess.run([sys.executable,'-m','src.connectors.sync','--worker',dataset_id,period or '',str(output)],
                  cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                  timeout=60,check=False)
                if process.returncode: raise ConnectorError('Adapter worker failed')
                rows=json.loads(read_regular(output,dataset['max_bytes']*2))
        else: rows=create_adapter(source).fetch(dataset,period)
        if not rows and not dataset.get('allow_empty',False): raise IncompleteSnapshot('Empty snapshot requires explicit dataset policy')
        if len(rows)>dataset['max_rows']: raise IncompleteSnapshot('Snapshot row limit reached')
        normalized=[];ids=set();payload_bytes=0
        for row in rows:
            row=project(row,dataset['fields'])
            rid=row.get(dataset['id_field'])
            if rid is None or str(rid)=='': raise ConnectorError('Stable source ID missing')
            rid=str(rid)
            if rid in ids: raise ConnectorError('Duplicate stable source IDs; snapshot refused')
            ids.add(rid);metadata=row_metadata(dataset,row)
            payload=json.dumps(canonical(row),sort_keys=True)
            payload_bytes+=len(payload.encode())
            if payload_bytes>dataset['max_bytes']: raise IncompleteSnapshot('Snapshot byte limit exceeded')
            normalized.append((rid,payload,json.dumps(metadata,sort_keys=True)))
        latest_source,latest_dataset=resolve(dataset_id)
        digest=fingerprint(source,dataset)
        if digest!=fingerprint(latest_source,latest_dataset): raise ConnectorError('Source catalog changed during sync')
        generation=str(uuid.uuid4());stamp=now()
        with db.connect() as conn:
            # Lock/serialize the local state row before publishing a new generation.
            db.execute(conn,'INSERT INTO eail_sync_state VALUES (?,?,?,?,?,?) ON CONFLICT(dataset_id,scope) DO NOTHING',
                       (dataset_id,scope,'',digest,'',''))
            if not db.url.startswith('sqlite:///'):
                db.execute(conn,'SELECT dataset_id FROM eail_sync_state WHERE dataset_id=? AND scope=? FOR UPDATE',(dataset_id,scope))
            db.execute(conn,'DELETE FROM eail_source_records WHERE dataset_id=? AND scope=?',(dataset_id,scope))
            for rid,payload,metadata in normalized:
                identity=hashlib.sha256((dataset_id+'\0'+scope+'\0'+rid).encode()).hexdigest()
                row=json.loads(payload);updated=row.get(dataset.get('updated_field','')) or ''
                db.execute(conn,'INSERT INTO eail_source_records VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (identity,source['id'],dataset_id,scope,rid,payload,metadata,str(updated),stamp,generation))
            db.execute(conn,'UPDATE eail_sync_state SET generation=?,catalog_hash=?,synced_at=?,last_error=? WHERE dataset_id=? AND scope=?',
                       (generation,digest,stamp,'',dataset_id,scope))
            db.execute(conn,"UPDATE eail_sync_runs SET status='success',finished_at=?,detail=? WHERE id=?",(stamp,str(len(rows))+' records',run_id))
        event('ingestion','source_synced',source_id=source['id'],dataset_id=dataset_id,scope=scope,rows=len(rows),seconds=round(time.monotonic()-start,3))
        return {'dataset_id':dataset_id,'scope':scope,'status':'success','records':len(rows),'generation':generation}
    except Exception as exc:
        with db.connect() as conn:
            db.execute(conn,"UPDATE eail_sync_runs SET status='failed',finished_at=?,detail=? WHERE id=?",(now(),type(exc).__name__,run_id))
            db.execute(conn,'UPDATE eail_sync_state SET last_error=? WHERE dataset_id=? AND scope=?',(type(exc).__name__,dataset_id,scope))
        event('ingestion','source_sync_failed',source_id=source['id'],dataset_id=dataset_id,error_type=type(exc).__name__)
        raise

def worker():
    dataset_id,period,output=sys.argv[2:5]
    source,dataset=resolve(dataset_id)
    rows=create_adapter(source).fetch(dataset,period or None)
    Path(output).write_text(json.dumps(canonical(rows)))
    Path(output).chmod(0o600)
if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='--worker': worker()
