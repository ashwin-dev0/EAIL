"""Trusted source/dataset catalog. Users and models select IDs, never DSNs/URLs/SQL."""
import hashlib,json,os,re
from pathlib import Path
from src.config import ROOT
from src.auth import validate_metadata
from src.file_safety import read_regular
from src.connectors.base import ConfigurationError,secret
KINDS={'sql','mongodb','zoho_books','zoho_crm','zoho_analytics','zoho_rest','tally'}
ID=re.compile(r'^[a-z][a-z0-9_-]{0,79}$')

def load_catalog():
    path=Path(os.getenv('CONNECTORS_FILE',str(ROOT/'config/connectors.json')))
    if not path.exists(): return {'sources':[],'datasets':[]}
    if path.is_symlink(): raise ConfigurationError('Connector catalog symlink rejected')
    if os.name=='posix' and path.stat().st_mode & 0o022: raise ConfigurationError('Connector catalog must not be group/world writable')
    data=json.loads(read_regular(path,1_000_000))
    if set(data)!={'sources','datasets'}: raise ConfigurationError('Invalid connector catalog')
    ids=set()
    for source in data['sources']:
        from src.connectors.extensions import ADAPTER_FACTORIES
        if not ID.fullmatch(source.get('id','')) or source.get('kind') not in KINDS | set(ADAPTER_FACTORIES) or source['id'] in ids:
            raise ConfigurationError('Invalid source registration')
        if type(source.get('enabled')) is not bool: raise ConfigurationError('Source enabled flag required')
        ids.add(source['id'])
        if source['kind']=='sql' and not source.get('readonly_credentials_confirmed'):
            raise ConfigurationError('SQL source requires a confirmed SELECT-only account')
        if source['kind']=='mongodb' and not source.get('readonly_credentials_confirmed'):
            raise ConfigurationError('MongoDB source requires a confirmed read-only account')
    seen=set()
    for dataset in data['datasets']:
        if not ID.fullmatch(dataset.get('id','')) or dataset['id'] in seen or dataset.get('source_id') not in ids:
            raise ConfigurationError('Invalid dataset registration')
        seen.add(dataset['id'])
        if type(dataset.get('enabled')) is not bool: raise ConfigurationError('Dataset enabled flag required')
        validate_metadata(dataset['metadata'])
        fields=dataset.get('fields')
        if not isinstance(fields,list) or not fields or len(fields)>50 or len(set(fields))!=len(fields) or not all(isinstance(f,str) and re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_.$-]{0,99}',f) for f in fields):
            raise ConfigurationError('Declare up to 50 explicit projected fields')
        if dataset.get('id_field') not in fields: raise ConfigurationError('Project the stable source ID field')
        for key,maximum in [('max_rows',10000),('max_bytes',10_000_000),('max_age_seconds',86400)]:
            value=dataset.get(key)
            if type(value) is not int or not 1<=value<=maximum: raise ConfigurationError('Invalid dataset resource limit')
        if dataset.get('sync_scope','all') not in {'all','period'}: raise ConfigurationError('Invalid sync scope')
        for metric in dataset.get('measures',[]):
            if set(metric)-{'name','field','operation','currency_field','unit','baseline_field'} or metric.get('operation') not in {'sum_decimal','difference_decimal'} or metric.get('field') not in fields or not metric.get('name') or not metric.get('unit'):
                raise ConfigurationError('Declare approved metric field, name, operation and unit')
            if metric.get('operation')=='difference_decimal' and metric.get('baseline_field') not in fields: raise ConfigurationError('Project the variance baseline field')
            if metric.get('currency_field') and metric['currency_field'] not in fields: raise ConfigurationError('Project the metric currency field')
        if type(dataset.get('allow_empty',False)) is not bool: raise ConfigurationError('Invalid empty-snapshot policy')
        acl=dataset.get('row_acl')
        if acl:
            if set(acl)-{'owner_field','allowed_users_field','allowed_roles_field','classification_field'}:
                raise ConfigurationError('Unknown row ACL mapping')
            if not all(v in fields for v in acl.values()): raise ConfigurationError('Project every row ACL field')
    return data

def resolve(dataset_id,principal=None):
    catalog=load_catalog()
    dataset=next((d for d in catalog['datasets'] if d['id']==dataset_id and d['enabled']),None)
    if not dataset: raise ConfigurationError('Dataset unavailable')
    source=next(s for s in catalog['sources'] if s['id']==dataset['source_id'])
    if not source['enabled']: raise ConfigurationError('Source unavailable')
    if principal and not principal.can_read(dataset['metadata']): raise PermissionError('Dataset access denied')
    return source,dataset

def fingerprint(source,dataset):
    dependencies={}
    for key,value in source.items():
        if key.endswith('_env'): dependencies[key]=hashlib.sha256(secret(value).encode()).hexdigest()
    if dataset.get('query_file'):
        file=(ROOT/dataset['query_file']).resolve()
        if not file.is_relative_to((ROOT/'config/sql').resolve()): raise ConfigurationError('Invalid source query location')
        dependencies['query_hash']=hashlib.sha256(read_regular(file,65536)).hexdigest()
    return hashlib.sha256(json.dumps({'source':source,'dataset':dataset,'dependencies':dependencies},sort_keys=True).encode()).hexdigest()

def create_adapter(source):
    from src.connectors.extensions import ADAPTER_FACTORIES
    if source['kind'] in ADAPTER_FACTORIES: return ADAPTER_FACTORIES[source['kind']](source)
    if source['kind']=='sql':
        from src.connectors.sql import SQLAdapter
        return SQLAdapter(source)
    if source['kind']=='mongodb':
        from src.connectors.sql import MongoAdapter
        return MongoAdapter(source)
    if source['kind']=='tally':
        from src.connectors.tally import TallyAdapter
        return TallyAdapter(source)
    from src.connectors.zoho import ZohoAdapter
    return ZohoAdapter(source)
