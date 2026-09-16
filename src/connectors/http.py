import json,time,random,urllib.parse
import httpx
from src.connectors.base import ConfigurationError,ConnectorError,SourceUnavailable

class SafeHTTP:
    def __init__(self,origins,max_bytes=10_000_000,timeout=20,client=None):
        self.origins=set(origins);self.max_bytes=max_bytes;self.timeout=timeout
        self.client=client or httpx.Client(verify=True,trust_env=False,follow_redirects=False,
            timeout=httpx.Timeout(timeout,connect=5),limits=httpx.Limits(max_connections=2,max_keepalive_connections=1))
    def close(self): self.client.close()
    def request(self,method,url,headers=None,params=None,data=None,content=None,retry=True):
        u=urllib.parse.urlsplit(url);origin=f'{u.scheme}://{u.netloc}'
        if origin not in self.origins or u.username or u.password or u.fragment:
            raise ConfigurationError('External endpoint is not approved')
        if method not in {'GET','POST'}: raise ConfigurationError('External write method refused')
        # POST is used ONLY by fixed OAuth refresh and Tally export callers.
        deadline=time.monotonic()+self.timeout
        for attempt in range(3 if retry else 1):
            try:
                with self.client.stream(method,url,headers=headers,params=params,data=data,content=content) as response:
                    if 300<=response.status_code<400: raise ConfigurationError('Redirects are refused')
                    status=response.status_code
                    body=bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic()>deadline: raise SourceUnavailable('Source deadline exceeded')
                        body.extend(chunk)
                        if len(body)>self.max_bytes: raise ConnectorError('Source response exceeds byte limit')
                    result=(status,dict(response.headers),bytes(body))
                if status not in {429,500,502,503,504} or not retry or attempt==2: return result
                raw=response.headers.get('retry-after','')
                delay=min(float(raw),5) if raw.isdigit() else min(2**attempt+random.random(),5)
                if time.monotonic()+delay>=deadline: raise SourceUnavailable('Source retry deadline exceeded')
                time.sleep(delay)
            except httpx.TransportError:
                # Do not include endpoint, credentials or upstream content in errors.
                if not retry or attempt==2: raise SourceUnavailable('Source transport failed')
                if time.monotonic()+.25>=deadline: raise SourceUnavailable('Source deadline exceeded')
                time.sleep(.25)
        raise SourceUnavailable('Source request failed')

def decode_json(status,body):
    if status==204: return {}
    if status==401: raise ConnectorError('Source credential rejected')
    if not 200<=status<300: raise SourceUnavailable('Source API rejected the read request')
    try: return json.loads(body,parse_float=str)
    except (ValueError,UnicodeError): raise ConnectorError('Source returned invalid JSON')
