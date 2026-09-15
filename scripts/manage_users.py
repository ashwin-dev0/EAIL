"""Local administrator credential provisioning. Tokens never stored in plaintext."""
import argparse, hashlib, json, os, secrets, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.config import settings
from src.auth import DEPARTMENTS

def main():
    p=argparse.ArgumentParser()
    p.add_argument('id');p.add_argument('--role',required=True)
    p.add_argument('--departments',nargs='+',choices=DEPARTMENTS,required=True)
    p.add_argument('--clearance',type=int,choices=range(4),default=1)
    p.add_argument('--ingest',action='store_true');p.add_argument('--approve',action='store_true')
    p.add_argument('--disable',action='store_true')
    a=p.parse_args()
    file=settings.users;file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if file.is_symlink(): raise SystemExit('Credential symlink rejected')
    data=json.loads(file.read_text()) if file.exists() else {'users':[]}
    old=next((u for u in data['users'] if u['id']==a.id),None)
    token=secrets.token_urlsafe(48)
    user={'id':a.id,'role':a.role,'departments':a.departments,'clearance':a.clearance,
        'ingest':a.ingest,'approve':a.approve,'enabled':not a.disable,
        'policy_version':old.get('policy_version',1)+1 if old else 1,
        'token_hash':hashlib.sha256(token.encode()).hexdigest()}
    data['users']=[u for u in data['users'] if u['id']!=a.id]+[user]
    fd,temp=tempfile.mkstemp(dir=file.parent,prefix='.users-')
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f: json.dump(data,f,indent=2)
        os.replace(temp,file)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    if not a.disable:
        print('New token (shown once; store privately):')
        print(token)
    else: print('User disabled; previous credential revoked.')
if __name__=='__main__': main()
