"""Opaque per-user credentials. Roles and grants always come from server storage."""
import hashlib, hmac, json, os
from dataclasses import dataclass
from src.config import settings

DEPARTMENTS = ('Finance','IT','Administration','Innovation','HR','Procurement','Compliance')
@dataclass(frozen=True)
class Principal:
    id: str
    role: str
    departments: tuple
    clearance: int
    ingest: bool = False
    approve: bool = False
    grants: tuple = ()
    policy_version: int = 1
    def can_read(self, meta):
        required = {'department','classification','owner','allowed_users','allowed_roles'}
        if not required <= meta.keys(): return False
        if meta['classification'] > self.clearance: return False
        if meta['department'] not in self.departments and meta['department'] != 'Public': return False
        scoped = bool(meta['allowed_users'] or meta['allowed_roles'])
        if scoped:
            return self.id == meta['owner'] or self.id in meta['allowed_users'] or self.role in meta['allowed_roles']
        return True
    def require_department(self, department):
        if department not in DEPARTMENTS or department not in self.departments: raise PermissionError('Department access denied')

def load_users(path=None):
    path = path or settings.users
    if not path.exists(): raise RuntimeError('Run scripts/manage_users.py to configure users')
    if os.name == 'posix' and path.stat().st_mode & 0o077: raise RuntimeError('User credentials require mode 600')
    data = json.loads(path.read_text())
    return data['users']

def authenticate(token, path=None):
    if not isinstance(token,str) or not 32 <= len(token) <= 8192: raise PermissionError('Invalid credentials')
    found=None
    if token.count('.')==2 and os.getenv('OIDC_PUBLIC_KEY_FILE'):
        # Offline JWT verification against an enterprise-managed local public key.
        # No automatic key downloads, remote introspection, or token-provided roles.
        import jwt
        from pathlib import Path
        try:
            claims=jwt.decode(token,Path(os.environ['OIDC_PUBLIC_KEY_FILE']).read_text(),
                algorithms=['RS256'],audience=os.environ['OIDC_AUDIENCE'],issuer=os.environ['OIDC_ISSUER'],
                options={'require':['exp','iat','sub','iss','aud']})
        except Exception: raise PermissionError('Invalid SSO credentials')
        found=next((u for u in load_users(path) if u['id']==claims['sub']),None)
    elif os.getenv('OIDC_ONLY','false').lower()!='true':
        digest=hashlib.sha256(token.encode()).hexdigest()
        for user in load_users(path):
            if hmac.compare_digest(user.get('token_hash',''),digest): found=user
    if not found or not found.get('enabled',False): raise PermissionError('Invalid credentials')
    return Principal(found['id'],found['role'],tuple(found['departments']),found['clearance'],
                     found.get('ingest',False),found.get('approve',False),tuple(found.get('grants',[])),found.get('policy_version',1))

def validate_metadata(meta):
    if not isinstance(meta,dict): raise ValueError('Metadata must be an object')
    expected={'department','classification','owner','allowed_users','allowed_roles'}
    if set(meta) != expected: raise ValueError('Metadata must explicitly declare all five ACL fields')
    if meta['department'] not in (*DEPARTMENTS,'Public'): raise ValueError('Unknown department')
    if type(meta['classification']) is not int or not 0 <= meta['classification'] <= 3: raise ValueError('Classification must be 0..3')
    if not isinstance(meta['owner'],str) or not meta['owner']: raise ValueError('Owner required')
    for key in ['allowed_users','allowed_roles']:
        if not isinstance(meta[key],list) or not all(isinstance(x,str) and len(x)<=100 for x in meta[key]):
            raise ValueError('Invalid ACL list')
    return meta
