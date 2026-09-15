"""Administrator-only normalized source import; never expose as an LLM tool."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.database import db
from src.auth import validate_metadata,DEPARTMENTS
from src.analytics import validate_period
from src.logging_setup import now,event

def import_file(path):
    if path.stat().st_size>10_000_000: raise ValueError('Import size limit')
    items=json.loads(path.read_text())
    if not isinstance(items,list) or len(items)>10000: raise ValueError('Import row limit')
    # Validate full import before committing anything.
    for item in items:
        if set(item)-{'source_updated_at'}!={'id','department','kind','period','payload','metadata'}: raise ValueError('Invalid fact fields')
        if not isinstance(item['id'],str) or not 1<=len(item['id'])<=100: raise ValueError('Invalid source ID')
        validate_period(item['period']);meta=validate_metadata(item['metadata'])
        if item.get('source_updated_at'):
            from datetime import datetime
            parsed=datetime.fromisoformat(item['source_updated_at'])
            if parsed.tzinfo is None: raise ValueError('Source timestamps require timezone')
        if item['department'] not in DEPARTMENTS or meta['department']!=item['department']: raise ValueError('Department mismatch')
        if item['kind']=='budget_actual':
            payload=item['payload']
            if set(payload)!={'category','currency','budget_minor','actual_minor'}: raise ValueError('Invalid budget payload')
            if type(payload['budget_minor']) is not int or type(payload['actual_minor']) is not int: raise ValueError('Use integer minor amounts')
            if not isinstance(payload['currency'],str) or len(payload['currency'])!=3: raise ValueError('Currency code required')
        if len(json.dumps(item['payload']))>20000: raise ValueError('Payload limit')
    with db.connect() as conn:
        for item in items:
            values=(item['id'],item['department'],item['kind'],item['period'],json.dumps(item['payload']),json.dumps(item['metadata']),now(),item.get('source_updated_at',''))
            db.execute(conn,'INSERT INTO eail_facts VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET department=excluded.department,kind=excluded.kind,period=excluded.period,payload=excluded.payload,metadata=excluded.metadata,updated_at=excluded.updated_at,source_updated_at=excluded.source_updated_at',values)
    event('ingestion','facts_imported',rows=len(items))
    return len(items)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);a=p.parse_args()
    print(f'Imported {import_file(a.file)} normalized facts')
