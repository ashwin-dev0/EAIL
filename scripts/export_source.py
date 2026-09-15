"""Example PostgreSQL-compatible source adapter.
An administrator provides a reviewed SELECT in a local file and a read-only DSN.
The source query must return normalized EAIL fact columns. It is never generated
by a model or provided by API clients. Writes go only to the local export file.
"""
import argparse,json,os,sys
from pathlib import Path

def main():
    import psycopg
    p=argparse.ArgumentParser();p.add_argument('--query',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--period',required=True);a=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from src.analytics import validate_period
    validate_period(a.period)
    dsn=os.environ['EAIL_SOURCE_DSN']
    query=a.query.read_text()
    # Security comes from source role grants/read-only transaction, not regex SQL checks.
    with psycopg.connect(dsn,connect_timeout=10) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout='10000ms'")
        with conn.cursor() as cursor:
            cursor.execute(query,{'period':a.period})
            names=[c.name for c in cursor.description];rows=cursor.fetchmany(10001)
            if len(rows)>10000: raise ValueError('Source row limit')
    output=[dict(zip(names,row)) for row in rows]
    a.output.write_text(json.dumps(output,indent=2))
    if os.name=='posix': a.output.chmod(0o600)
    print(f'Exported {len(output)} rows. Review and import with scripts/import_facts.py.')
if __name__=='__main__': main()
