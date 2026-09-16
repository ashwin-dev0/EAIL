import base64,datetime,decimal,json,math,re,time
from abc import ABC,abstractmethod
class ConnectorError(RuntimeError): pass
class ConfigurationError(ConnectorError): pass
class AuthenticationError(ConnectorError): pass
class IncompleteSnapshot(ConnectorError): pass
class SourceUnavailable(ConnectorError): pass
class Adapter(ABC):
    @abstractmethod
    def fetch(self,dataset,period=None):
        """Return a COMPLETE bounded snapshot; raise before truncation."""

def secret(name):
    import os
    if not isinstance(name,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{1,99}',name):
        raise ConfigurationError('Invalid secret reference')
    value=os.getenv(name)
    if not value: raise ConfigurationError('Required connector secret is missing')
    return value

def canonical(value):
    # Preserve decimal values as strings, never silently round financial amounts.
    if value is None or type(value) in {str,int,bool}: return value
    if isinstance(value,float):
        if not math.isfinite(value): raise ConnectorError('Non-finite source number')
        return str(value)
    if isinstance(value,decimal.Decimal): return str(value)
    if isinstance(value,(datetime.datetime,datetime.date)): return value.isoformat()
    if isinstance(value,(bytes,bytearray)): return base64.b64encode(value).decode()
    if isinstance(value,dict): return {str(k):canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [canonical(v) for v in value]
    return str(value)

def get_field(record,path):
    value=record
    for part in path.split('.'):
        if not isinstance(value,dict) or part not in value: return None
        value=value[part]
    return value

def project(record,fields): return {field:canonical(get_field(record,field)) for field in fields}
def bounded(records,dataset):
    if len(records)>dataset['max_rows']: raise IncompleteSnapshot('Row limit reached; narrow the source dataset')
    if sum(len(json.dumps(canonical(row))) for row in records)>dataset['max_bytes']:
        raise IncompleteSnapshot('Snapshot byte limit reached')
    return records

class Snapshot(list):
    """Incremental bounds without O(n squared) rescans."""
    def __init__(self,dataset): super().__init__();self.dataset=dataset;self.bytes=0
    def append(self,row):
        size=len(json.dumps(canonical(row)))
        if len(self)+1>self.dataset['max_rows'] or self.bytes+size>self.dataset['max_bytes']:
            raise IncompleteSnapshot('Complete snapshot exceeds configured bounds')
        self.bytes+=size;super().append(row)
    def extend(self,rows):
        for row in rows: self.append(row)
