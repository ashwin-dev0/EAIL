"""Approved structured tools. Amounts are integer minor currency units."""
import json, re, hashlib
from decimal import Decimal, ROUND_HALF_UP
from src.auth import DEPARTMENTS, validate_metadata
from src.database import db
from src.guardrails.checks import injection

def fact_fingerprint(row):
    payload=row['payload']
    if isinstance(payload,str): payload=json.loads(payload)
    metadata=row['metadata']
    if isinstance(metadata,str): metadata=json.loads(metadata)
    return hashlib.sha256(json.dumps({'payload':payload,'metadata':metadata,'department':row['department'],'period':row['period'],'kind':row['kind'],'synced_at':row['updated_at'],'source_updated_at':row.get('source_updated_at','')},sort_keys=True).encode()).hexdigest()

def structured_still_valid(results,principal):
    for result in results:
        if result.get('tool')=='source_records':
            from src.connectors.query import snapshot_still_valid
            if not snapshot_still_valid(result,principal): return False
            continue
        for source in result.get('sources',[]):
            rows=db.rows('SELECT * FROM eail_facts WHERE id=?',(source['id'],))
            if not rows or not principal.can_read(json.loads(rows[0]['metadata'])) or fact_fingerprint(rows[0])!=source['fingerprint']:
                return False
    return True

PERIOD=re.compile(r'^(?:\d{4}-(?:0[1-9]|1[0-2])|\d{4}-Q[1-4])$')
def validate_period(value):
    if not isinstance(value,str) or not PERIOD.fullmatch(value): raise ValueError('Use explicit YYYY-MM or YYYY-Qn period')
    return value

def permitted_facts(principal,department,period,kind=None):
    principal.require_department(department);validate_period(period)
    sql='SELECT * FROM eail_facts WHERE department=? AND period=?'
    args=[department,period]
    if kind: sql+=' AND kind=?';args.append(kind)
    rows=db.rows(sql+' ORDER BY id LIMIT 10001',args)
    if len(rows)>10000: raise ValueError('Fact query row limit')
    result=[];excluded=0;payload_bytes=0
    for row in rows:
        payload_bytes+=len(row['payload'])
        if payload_bytes>2_000_000: raise ValueError('Structured result exceeds evidence budget; narrow the query')
        meta=validate_metadata(json.loads(row['metadata']))
        if not principal.can_read(meta): excluded+=1;continue
        if injection(row['payload']): excluded+=1;continue
        row['payload']=json.loads(row['payload']);result.append(row)
    return result,excluded

def budget_variance(principal,department,period):
    rows,excluded=permitted_facts(principal,department,period,'budget_actual')
    if not rows: return {'tool':'budget_variance','department':department,'period':period,'status':'no_authorized_data','excluded_records':excluded}
    currencies={r['payload']['currency'] for r in rows}
    if len(currencies)!=1: raise ValueError('Mixed currencies require approved conversion; refused')
    budget=actual=0;categories=[]
    for row in rows:
        p=row['payload']; b=p['budget_minor'];a=p['actual_minor']
        if type(b) is not int or type(a) is not int: raise ValueError('Amounts must be integer minor units')
        budget+=b;actual+=a
        categories.append({'category':p['category'],'budget_minor':b,'actual_minor':a,'variance_minor':a-b,'source_id':row['id']})
    percent=str((Decimal(actual-budget)*100/Decimal(budget)).quantize(Decimal('.01'))) if budget else None
    return {'tool':'budget_variance','status':'ok','department':department,'period':period,
            'currency':next(iter(currencies)),'budget_minor':budget,'actual_minor':actual,
            'variance_minor':actual-budget,'variance_percent':percent,
            'definition':'actual minus approved budget; amounts in minor units',
            'categories':sorted(categories,key=lambda x:x['variance_minor'],reverse=True),
            'sources':[{'id':r['id'],'updated_at':r['updated_at'],'source_updated_at':r.get('source_updated_at',''),'fingerprint':fact_fingerprint(r)} for r in rows],
            'excluded_records':excluded,'scope':'authorized records only'}

def department_summary(principal,department,period):
    rows,excluded=permitted_facts(principal,department,period)
    return {'tool':'department_summary','status':'ok' if rows else 'no_authorized_data',
            'department':department,'period':period,'records':[
                {'source_id':r['id'],'kind':r['kind'],'data':r['payload'],'updated_at':r['updated_at'],'source_updated_at':r.get('source_updated_at','')} for r in rows[:50]],
            'sources':[{'id':r['id'],'updated_at':r['updated_at'],'source_updated_at':r.get('source_updated_at',''),'fingerprint':fact_fingerprint(r)} for r in rows[:50]],'matching_records':len(rows),'truncated':len(rows)>50,'excluded_records':excluded,'scope':'authorized records only'}

def budget_scenario(principal,department,period,change_percent):
    if type(change_percent) not in {int,float} or not -100<=change_percent<=100:
        raise ValueError('Scenario change must be -100..100 percent')
    result=budget_variance(principal,department,period)
    if result['status']!='ok': return result
    adjusted=int((Decimal(result['actual_minor'])*(1+Decimal(str(change_percent))/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    return {'tool':'budget_scenario','status':'ok','baseline':result,'change_percent':change_percent,
            'scenario_actual_minor':adjusted,'scenario_variance_minor':adjusted-result['budget_minor'],
            'assumption':'Uniform change applied to recorded actual spending; hypothetical, not a forecast'}

def forecast_spend(principal,department,period):
    """Transparent three-month moving average, with simple rolling backtest."""
    principal.require_department(department);validate_period(period)
    if '-Q' in period: raise ValueError('Forecast target must be YYYY-MM')
    year,month=map(int,period.split('-'));index=year*12+month-1
    totals=[];all_rows=[];currencies=set();excluded=0
    for target in range(index-6,index):
        y,m=divmod(target,12);historical=f'{y:04d}-{m+1:02d}'
        rows,hidden=permitted_facts(principal,department,historical,'budget_actual');excluded+=hidden
        if not rows or hidden: raise ValueError('Forecast needs six complete authorized consecutive monthly periods')
        total=0
        for row in rows:
            payload=row['payload'];value=payload['actual_minor']
            if type(value) is not int: raise ValueError('Invalid historical amount')
            currencies.add(payload['currency']);total+=value
        totals.append(total);all_rows.extend(rows)
    if len(currencies)!=1: raise ValueError('Mixed historical currencies refused')
    prediction=int((Decimal(sum(totals[-3:]))/3).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    errors=[abs(Decimal(totals[i])-Decimal(sum(totals[i-3:i]))/3) for i in range(3,6)]
    mae=int((sum(errors)/len(errors)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    return {'tool':'forecast_spend','status':'ok','department':department,'period':period,
        'currency':next(iter(currencies)),'predicted_actual_minor':prediction,'backtest_mae_minor':mae,
        'history_actual_minor':totals,'method':'Three-month moving average; three rolling backtest observations',
        'assumption':'Baseline projection assumes recent average continues. No causal, seasonal, or confidence-interval claim.',
        'sources':[{'id':row['id'],'updated_at':row['updated_at'],'source_updated_at':row.get('source_updated_at',''),'fingerprint':fact_fingerprint(row)} for row in all_rows],
        'excluded_records':excluded,'scope':'complete authorized monthly history'}

def read_source(principal,dataset_id,period,limit):
    from src.connectors.query import source_records
    return source_records(principal,dataset_id,period,limit)

TOOLS={
 'source_records':{'function':read_source,'description':'Read authorized synchronized Zoho, Tally or database records by approved dataset ID; return deterministic measures and source provenance.',
 'parameters':{'type':'object','properties':{'dataset_id':{'type':'string'},'period':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':100}},'required':['dataset_id','period','limit'],'additionalProperties':False}},
 'forecast_spend':{'function':forecast_spend,'description':'Baseline next-period spending projection; requires six complete consecutive monthly periods.',
 'parameters':{'type':'object','properties':{'department':{'type':'string','enum':list(DEPARTMENTS)},'period':{'type':'string'}},'required':['department','period'],'additionalProperties':False}},
 'budget_variance':{'function':budget_variance,'description':'Calculate actual minus budget for one department and explicit period.',
 'parameters':{'type':'object','properties':{'department':{'type':'string','enum':list(DEPARTMENTS)},'period':{'type':'string'}},'required':['department','period'],'additionalProperties':False}},
 'department_summary':{'function':department_summary,'description':'Read authorized department records for one explicit period.',
 'parameters':{'type':'object','properties':{'department':{'type':'string','enum':list(DEPARTMENTS)},'period':{'type':'string'}},'required':['department','period'],'additionalProperties':False}},
 'budget_scenario':{'function':budget_scenario,'description':'Calculate a hypothetical change in recorded actual spending.',
 'parameters':{'type':'object','properties':{'department':{'type':'string','enum':list(DEPARTMENTS)},'period':{'type':'string'},'change_percent':{'type':'number','minimum':-100,'maximum':100}},'required':['department','period','change_percent'],'additionalProperties':False}}
}
def dispatch(name,args,principal):
    if name not in TOOLS: raise ValueError('Tool is not allowlisted')
    schema=TOOLS[name]['parameters']
    if set(args)!=set(schema['required']): raise ValueError('Tool arguments do not match schema')
    authorize_tool(name,args,principal)
    return TOOLS[name]['function'](principal,**args)

def authorize_tool(name,args,principal):
    if name not in TOOLS or set(args)!=set(TOOLS[name]['parameters']['required']): raise ValueError('Invalid tool call')
    if name=='source_records':
        from src.connectors.registry import resolve
        resolve(args['dataset_id'],principal)
        if args['period']: validate_period(args['period'])
        if type(args['limit']) is not int or not 1<=args['limit']<=100: raise ValueError('Invalid source limit')
    else:
        principal.require_department(args['department']);validate_period(args['period'])
