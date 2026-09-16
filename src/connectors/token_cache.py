"""Encrypted cross-process OAuth cache; never share a refresh-token namespace."""
import hashlib,json,os,tempfile,time
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from src.config import ROOT
from src.file_safety import read_regular
from src.connectors.base import secret,ConfigurationError

@contextmanager
def locked_cache(source):
    if os.name!='posix': raise ConfigurationError('Persistent token-cache locking currently requires POSIX')
    import fcntl
    key=secret(source['token_cache_key_env'])
    try: cipher=Fernet(key.encode())
    except Exception: raise ConfigurationError('Invalid OAuth cache encryption key')
    path=Path(os.getenv('ZOHO_TOKEN_CACHE_FILE',str(ROOT/'data/zoho_tokens.enc')))
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink() or path.parent.is_symlink(): raise ConfigurationError('OAuth cache symlink rejected')
    lock_path=path.with_name(path.name+'.lock')
    fd=os.open(lock_path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        if path.exists():
            if path.stat().st_mode & 0o077: raise ConfigurationError('OAuth cache must have mode 600')
            try: data=json.loads(cipher.decrypt(read_regular(path,1_000_000)))
            except (InvalidToken,ValueError): raise ConfigurationError('OAuth cache cannot be decrypted; rotate or remove through administration')
        else: data={}
        yield data
        data={k:v for k,v in data.items() if v.get('expires_at',0)>time.time()}
        output=cipher.encrypt(json.dumps(data).encode())
        temp_fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.oauth-')
        try:
            os.fchmod(temp_fd,0o600)
            with os.fdopen(temp_fd,'wb') as file: file.write(output)
            os.replace(temp,path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def cache_identity(source):
    return hashlib.sha256((source['region']+'\0'+secret(source['client_id_env'])+'\0'+secret(source['refresh_token_env'])).encode()).hexdigest()
