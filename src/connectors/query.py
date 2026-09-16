"""Read locally synchronized records through enterprise ACLs and fixed measures."""
import datetime,json,re
from decimal import Decimal,InvalidOperation
from src.database import db
from src.auth import validate_metadata
from src.connectors.registry import resolve,fingerprint,load_catalog
from src.connectors.base import ConfigurationError,SourceUnavailable
from src.guardrails.checks import injection

def fresh_state(source,dataset,scope):
    states=db.rows('SELECT * FROM eail_sync_state WHERE dataset_id=? AND scope=?',(dataset['id'],scope))
    if not states or not states[0]['generation']: raise SourceUnavailable('Dataset is not synchronized')
    state=states[0]
    if state['catalog_hash']!=fingerprint(source,dataset): raise SourceUnavailable('Source policy changed; synchronize again')
    timestamp=datetime.datetime.fromisoformat(state['synced_at'])
    age=(datetime.datetime.now(datetime.timezone.utc)-timestamp).total_seconds()
    if age < -60 or age>dataset['max_age_seconds']: raise SourceUnavailable('Snapshot freshness limit exceeded')
    return state

def matches_period(value,period):
    if not period: return True
    text=str(value or '')
    match=re.match(r'^(\d{4})-?(\d{2})',text)
    if not match: return False
    year,month=match.groups()
    return f'{year}-{month}'==period if '-Q' not in period else f'{year}-Q{(int(month)-1)//3+1}'==period

def source_records(principal,dataset_id,period='',limit=50):
    if type(limit) is not int or not 1<=limit<=100: raise ValueError('Limit must be 1..100')
    if period:
        from src.analytics import validate_period
        validate_period(period)
    source,dataset=resolve(dataset_id,principal)
    scope=period if dataset.get('sync_scope','all')=='period' else ''
    if dataset.get('sync_scope','all')=='period' and not period: raise ValueError('Period-scoped dataset requires an explicit period')
    state=fresh_state(source,dataset,scope)
    rows=db.rows('SELECT * FROM eail_source_records WHERE dataset_id=? AND scope=? ORDER BY source_record_id LIMIT 10001',(dataset_id,scope))
    authorized=[];excluded=0
    for row in rows:
        meta=validate_metadata(json.loads(row['metadata']))
        if not principal.can_read(meta) or injection(row['payload']): excluded+=1;continue
        payload=json.loads(row['payload'])
        if dataset.get('period_field') and not matches_period(payload.get(dataset['period_field']),period): continue
        authorized.append((row,payload))
    measures=[]
    for metric in dataset.get('measures',[]):
        if metric.get('operation') not in {'sum_decimal','difference_decimal'} or metric.get('field') not in dataset['fields']:
            raise ConfigurationError('Metric is not an approved sum over a projected field')
        grouped={}
        for row,payload in authorized:
            currency_value=payload.get(metric['currency_field']) if metric.get('currency_field') else 'unspecified'
            if currency_value is None or str(currency_value)=='': raise SourceUnavailable('Currency is missing; aggregation refused')
            currency=str(currency_value)
            raw=payload.get(metric['field'])
            try: value=Decimal(str(raw))
            except (InvalidOperation,TypeError): raise SourceUnavailable('Source amount is not a plain decimal; no guessed conversion')
            if not value.is_finite(): raise SourceUnavailable('Invalid source amount')
            if metric['operation']=='difference_decimal':
                try: baseline=Decimal(str(payload.get(metric['baseline_field'])))
                except (InvalidOperation,TypeError): raise SourceUnavailable('Variance baseline is not a plain decimal')
                if not baseline.is_finite(): raise SourceUnavailable('Invalid variance baseline')
                value-=baseline
            grouped[currency]=grouped.get(currency,Decimal(0))+value
        measures.append({'name':metric['name'],'field':metric['field'],'operation':metric['operation'],
                        'unit':metric['unit'],'by_currency':{k:str(v) for k,v in grouped.items()}})
    warnings=[]
    if state['last_error']: warnings.append('The latest sync failed; this is the last successful snapshot within the configured freshness limit.')
    if period and not dataset.get('period_field') and dataset.get('sync_scope','all')!='period':
        warnings.append('This master dataset is current-state data and is not filtered by the requested period.')
    return {'tool':'source_records','status':'ok','department':dataset['metadata']['department'],
       'source_id':source['id'],'dataset_id':dataset_id,'period':period,'scope':'authorized synchronized records only',
       'records':[{'id':r['id'],'source_record_id':r['source_record_id'],'data':payload,
         'source_updated_at':r['source_updated_at']} for r,payload in authorized[:limit]],
       'matching_records':len(authorized),'truncated':len(authorized)>limit,'excluded_records':excluded,
       'measures':measures,'warnings':warnings,'synced_at':state['synced_at'],
       'sources':[{'id':r['id'],'source_record_id':r['source_record_id'],'source_updated_at':r['source_updated_at']} for r,_ in authorized[:limit]],'source_count':len(authorized),
       'snapshot':{'dataset_id':dataset_id,'scope':scope,'generation':state['generation'],'catalog_hash':state['catalog_hash']}}

def snapshot_still_valid(result,principal):
    try:
        source,dataset=resolve(result['dataset_id'],principal);state=fresh_state(source,dataset,result['snapshot']['scope'])
        return state['generation']==result['snapshot']['generation'] and state['catalog_hash']==result['snapshot']['catalog_hash']
    except Exception: return False

def list_datasets(principal):
    catalog=load_catalog();sources={s['id']:s for s in catalog['sources'] if s['enabled']}
    return [{'id':d['id'],'source_id':d['source_id'],'kind':sources[d['source_id']]['kind'],
        'department':d['metadata']['department'],'fields':d['fields']} for d in catalog['datasets']
        if d['enabled'] and d['source_id'] in sources and principal.can_read(d['metadata'])]
