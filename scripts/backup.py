"""SQLite consistent backup, or PostgreSQL pg_dump via environment credentials."""
import datetime,os,sqlite3,subprocess,sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.config import settings,ROOT

def main():
    directory=ROOT/'backups';directory.mkdir(exist_ok=True,mode=0o700)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    url=settings.database_url
    if url.startswith('sqlite:///'):
        output=directory/(stamp+'.sqlite')
        with sqlite3.connect(url[len('sqlite:///'):]) as source,sqlite3.connect(output) as target: source.backup(target)
    else:
        u=urlsplit(url);env=os.environ.copy()
        env.update(PGHOST=u.hostname,PGPORT=str(u.port or 5432),PGUSER=unquote(u.username),PGPASSWORD=unquote(u.password or ''),PGDATABASE=u.path.lstrip('/'))
        for key,value in parse_qs(u.query).items():
            if key in {'sslmode','sslrootcert'}: env['PG'+key.upper()]=value[0]
        output=directory/(stamp+'.dump')
        subprocess.run(['pg_dump','--format=custom','--file',str(output)],env=env,check=True,timeout=300)
    output.chmod(0o600);print(output)
if __name__=='__main__': main()
