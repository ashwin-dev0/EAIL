import hashlib, json, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from src.config import settings, ROOT
from src.database import db
from src.file_safety import snapshot, EXTENSIONS, read_regular
from src.embeddings import encode, embedding_id
from src.chunking import chunk_text
from src.logging_setup import now,event

def record(name,state,detail):
    with db.connect() as conn:
        db.execute(conn,'INSERT INTO eail_ingestion VALUES (?,?,?,?,?)',(str(uuid.uuid4()),name,state,detail,now()))
    event('ingestion',state,name=name,detail=detail)

def deactivate(name,reason):
    with db.connect() as conn:
        db.execute(conn,'UPDATE eail_documents SET active=0 WHERE name=?',(name,))
    event('ingestion','deactivated',name=name,reason=reason)

def ingest_file(name,principal=None):
    begin=time.monotonic()
    try:
        path,data,meta=snapshot(name)
        if principal:
            if not principal.ingest: raise PermissionError('Ingestion permission required')
            principal.require_department(meta['department']) if meta['department']!='Public' else None
            if meta['classification']>principal.clearance: raise PermissionError('Classification access denied')
            if meta['owner']!=principal.id: raise PermissionError('Uploader must own supplied metadata')
        digest=hashlib.sha256(data).hexdigest(); meta_json=json.dumps(meta,sort_keys=True)
        existing=db.rows('SELECT * FROM eail_documents WHERE name=?',(name,))
        old=existing[0] if existing else None
        if old and old['content_hash']==digest and old['embedding_id']==embedding_id():
            with db.connect() as conn:
                db.execute(conn,'UPDATE eail_documents SET metadata=?,active=1,updated_at=? WHERE name=?',(meta_json,now(),name))
            record(name,'skipped','content unchanged; ACL refreshed');return True
        record(name,'running','extracting')
        with tempfile.TemporaryDirectory(prefix='eail-extract-') as tmp:
            source=Path(tmp)/('source'+path.suffix.lower());source.write_bytes(data)
            output=Path(tmp)/'sections.json'
            proc=subprocess.run([sys.executable,'-m','src.extractors.multiformat',str(source),str(output)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=settings.extraction_timeout,check=False)
            if proc.returncode: raise ValueError('Extractor failed; check installed format dependencies')
            sections=json.loads(read_regular(output,settings.max_text*8))
        extraction_time=time.monotonic()-begin
        prepared=[]
        for label,text in sections:
            for i,chunk in enumerate(chunk_text(text)):
                prepared.append((label,i,chunk))
        if not prepared: raise ValueError('No extractable content; existing version preserved')
        if len(prepared)>20000: raise ValueError('Chunk count limit')
        vectors=encode([x[2] for x in prepared]); embedded=time.monotonic()
        # Detect source/ACL changes during processing. Never commit an obsolete snapshot.
        _,latest,latest_meta=snapshot(name)
        if hashlib.sha256(latest).hexdigest()!=digest or latest_meta!=meta:
            raise ValueError('Source changed during ingestion; retry later')
        document_id=old['id'] if old else str(uuid.uuid4())
        version=old['version']+1 if old else 1
        with db.connect() as conn:
            # Optimistic version check protects concurrent ingestion processes.
            current=db.execute(conn,'SELECT version FROM eail_documents WHERE name=?',(name,)).fetchone()
            if (current is not None) != (old is not None) or (current and current['version']!=old['version']):
                raise ValueError('Concurrent ingestion; retry later')
            if old:
                changed=db.execute(conn,'UPDATE eail_documents SET content_hash=?,version=?,metadata=?,embedding_id=?,active=1,updated_at=? WHERE id=? AND version=?',
                           (digest,version,meta_json,embedding_id(),now(),document_id,old['version'])).rowcount
                if changed!=1: raise ValueError('Concurrent document replacement; retry later')
                db.execute(conn,'DELETE FROM eail_chunks WHERE document_id=?',(document_id,))
            else:
                db.execute(conn,'INSERT INTO eail_documents VALUES (?,?,?,?,?,?,?,?)',
                           (document_id,name,digest,version,meta_json,embedding_id(),1,now()))
            for (label,i,text),vector in zip(prepared,vectors):
                db.execute(conn,'INSERT INTO eail_chunks VALUES (?,?,?,?,?,?)',
                           (str(uuid.uuid4()),document_id,label,i,text,json.dumps(vector)))
        record(name,'success',f'{len(prepared)} chunks; version {version}')
        event('ingestion','timings',name=name,extraction_seconds=round(extraction_time,3),
              embedding_seconds=round(embedded-begin-extraction_time,3),total_seconds=round(time.monotonic()-begin,3))
        return True
    except PermissionError: raise
    except Exception as exc:
        # Invalid/revoked ACLs must not leave an old readable version active.
        try: snapshot(name)
        except Exception: deactivate(name,'invalid or missing source/ACL')
        record(name,'failed',type(exc).__name__);return False

def reconcile():
    settings.documents.mkdir(parents=True,exist_ok=True)
    for item in sorted(settings.documents.iterdir()):
        if item.name.lower().endswith(".meta.json"):
            continue
        if item.suffix.lower() in EXTENSIONS: ingest_file(item.name)
    for old in db.rows('SELECT name FROM eail_documents WHERE active=1'):
        if not (settings.documents/old['name']).exists(): deactivate(old['name'],'deleted')

if __name__=='__main__':
    db.verify()
    if len(sys.argv)>1: raise SystemExit(0 if ingest_file(sys.argv[1]) else 1)
    reconcile()
