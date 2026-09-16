"""Zoho Books v3, CRM v8, Analytics v2 and administrator-approved REST reads."""
import json,re,threading,time,urllib.parse
from src.connectors.base import Adapter,Snapshot,secret,project,bounded,ConfigurationError,AuthenticationError,IncompleteSnapshot,ConnectorError
from src.connectors.http import SafeHTTP,decode_json
REGIONS={'com','in','eu','com.au','jp','ca','com.cn','sa'}
BOOKS={'invoices','bills','contacts','expenses','purchaseorders','salesorders','items','estimates','customerpayments','vendorpayments','creditnotes','vendorcredits','chartofaccounts','journals'}
ID=re.compile(r'^\d{1,40}$')

def zoho_origins(region):
    if region not in REGIONS: raise ConfigurationError('Invalid Zoho data-center region')
    return f'https://accounts.zoho.{region}',f'https://www.zohoapis.{region}',('https://analyticsapi.zohocloud.ca' if region=='ca' else f'https://analyticsapi.zoho.{region}')

class ZohoOAuth:
    def __init__(self,source,http): self.source=source;self.http=http;self.token=None;self.expires=0;self.lock=threading.Lock()
    def access(self,force=False):
        with self.lock:
            if self.token and time.monotonic()<self.expires and not force: return self.token
            if self.source.get('token_cache_key_env'):
                from src.connectors.token_cache import locked_cache,cache_identity
                with locked_cache(self.source) as cache:
                    identity=cache_identity(self.source);entry=cache.get(identity)
                    if entry and entry['expires_at']>time.time()+60 and not force:
                        self.token=entry['access_token'];self.expires=time.monotonic()+entry['expires_at']-time.time()-60
                        return self.token
                    token=self.refresh()
                    cache[identity]={'access_token':token,'expires_at':time.time()+max(1,self.expires-time.monotonic()+60)}
                    return token
            return self.refresh()
    def refresh(self):
        account,_,_=zoho_origins(self.source['region'])
        if self.source['kind']=='zoho_analytics' and self.source['region']=='ca': account='https://accounts.zohocloud.ca'
        status,_,body=self.http.request('POST',account+'/oauth/v2/token',params={
            'grant_type':'refresh_token','client_id':secret(self.source['client_id_env']),
            'client_secret':secret(self.source['client_secret_env']),'refresh_token':secret(self.source['refresh_token_env'])},retry=False)
        data=decode_json(status,body)
        if not isinstance(data,dict) or not data.get('access_token') or data.get('error'):
            raise AuthenticationError('Zoho OAuth refresh rejected')
        if '\r' in data['access_token'] or '\n' in data['access_token']: raise AuthenticationError('Invalid Zoho token')
        _,expected,_=zoho_origins(self.source['region'])
        if data.get('api_domain') and data['api_domain'].rstrip('/')!=expected:
            raise ConfigurationError('Zoho token belongs to a different data center')
        self.token=data['access_token'];self.expires=time.monotonic()+max(1,min(int(data.get('expires_in',3600)),3600)-60)
        return self.token

class ZohoAdapter(Adapter):
    def __init__(self,source,http=None):
        self.source=source;self.accounts,self.api,self.analytics=zoho_origins(source['region'])
        if source['kind']=='zoho_analytics' and source['region']=='ca': self.accounts='https://accounts.zohocloud.ca'
        origins=[self.accounts,self.api,self.analytics]
        if source['kind']=='zoho_rest':
            base=source['base_url'].rstrip('/');u=urllib.parse.urlsplit(base)
            allowed=source.get('approved_hosts',[])
            if u.scheme!='https' or u.hostname not in allowed or u.username or u.password or u.query or u.fragment:
                raise ConfigurationError('Approve the exact HTTPS Zoho product host')
            if not (u.hostname.endswith('.zoho.'+source['region']) or u.hostname.endswith('.zohoapis.'+source['region'])):
                raise ConfigurationError('REST product host must be in the selected Zoho region')
            self.base=base;origins.append(f'{u.scheme}://{u.netloc}')
        self.http=http or SafeHTTP(origins);self.oauth=ZohoOAuth(source,self.http)
    def get(self,url,params,headers=None):
        for attempt in range(2):
            if any(k.lower() in {'authorization','cookie','proxy-authorization'} for k in (headers or {})):
                raise ConfigurationError('Dataset must not override credential headers')
            h={'Authorization':'Zoho-oauthtoken '+self.oauth.access(force=attempt==1),**(headers or {})}
            status,_,body=self.http.request('GET',url,headers=h,params=params)
            if status==401 and attempt==0: continue
            return status,body
        raise AuthenticationError('Zoho credential rejected')
    def fetch(self,dataset,period=None):
        try:
            kind=self.source['kind']
            if kind=='zoho_analytics': return self.analytics_rows(dataset)
            if kind=='zoho_books':
                resource=dataset['resource']
                if resource not in BOOKS: raise ConfigurationError('Zoho Books resource is not approved')
                org=self.source['organization_id']
                if not ID.fullmatch(org): raise ConfigurationError('Zoho organization ID required')
                return self.paginated(dataset,self.api+'/books/v3/'+resource,{'organization_id':org},resource,'books')
            if kind=='zoho_crm':
                module=dataset['resource']
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',module): raise ConfigurationError('Invalid CRM module')
                return self.paginated(dataset,self.api+'/crm/v8/'+module,{'fields':','.join(dataset['fields'])},'data','crm')
            path=dataset['path']
            if not path.startswith('/') or '..' in path or '?' in path or '#' in path or '\\' in path or '://' in path:
                raise ConfigurationError('Invalid approved REST path')
            return self.paginated(dataset,self.base+path,dataset.get('params',{}),dataset['records_key'],dataset.get('pagination','none'))
        finally: self.http.close()
    def paginated(self,dataset,url,params,key,mode):
        records=Snapshot(dataset);page=1;next_token=None;seen=set()
        for attempt in range(100):
            query=dict(params)
            if mode in {'books','crm','page'}:
                query['per_page']=200
                if mode=='crm' and page>10:
                    if not next_token: raise IncompleteSnapshot('CRM requires a continuation token')
                    query['page_token']=next_token
                else: query['page']=page
            status,body=self.get(url,query,dataset.get('headers',{}))
            data=decode_json(status,body)
            if status==204: return records
            if not isinstance(data,dict) or ('code' in data and data['code'] not in {0,'0'}): raise ConnectorError('Zoho API application error')
            rows=data.get(key)
            if not isinstance(rows,list): raise ConnectorError('Zoho response does not contain the approved record list')
            records.extend(project(row,dataset['fields']) for row in rows)
            if mode=='books' or mode=='page':
                context=data.get('page_context',{})
                if type(context.get('has_more_page')) is not bool: raise IncompleteSnapshot('Missing Zoho pagination completion marker')
                more=context['has_more_page']
            elif mode=='crm':
                info=data.get('info',{})
                if type(info.get('more_records')) is not bool: raise IncompleteSnapshot('Missing CRM pagination completion marker')
                more=info['more_records']
                candidate=info.get('next_page_token')
                if candidate: next_token=candidate
                if page>=10 and more:
                    if not next_token or next_token in seen: raise IncompleteSnapshot('CRM pagination token did not advance')
                    seen.add(next_token)
            else:
                # Generic endpoints must declare completion; never assume a first
                # page of an unknown Zoho product represents its complete dataset.
                if dataset.get('single_response_complete') is not True: raise IncompleteSnapshot('Declare or implement product pagination')
                more=False
            if not more: return records
            if not rows: raise IncompleteSnapshot('Empty page with continuation flag')
            page+=1
        raise IncompleteSnapshot('Zoho page limit reached')
    def analytics_rows(self,dataset):
        for value in [self.source['organization_id'],dataset['workspace_id'],dataset['view_id']]:
            if not ID.fullmatch(value): raise ConfigurationError('Analytics organization/workspace/view IDs required')
        config={'responseFormat':'json','keyValueFormat':True,'selectedColumns':dataset['fields'],
            'showHiddenCols':False,'showPersonalCols':False,'validateSystemTags':True}
        if dataset.get('criteria'): config['criteria']=dataset['criteria']
        url=f"{self.analytics}/restapi/v2/workspaces/{dataset['workspace_id']}/views/{dataset['view_id']}/data"
        status,body=self.get(url,{'CONFIG':json.dumps(config)},{'ZANALYTICS-ORGID':self.source['organization_id']})
        data=decode_json(status,body)
        if isinstance(data,list): rows=data
        elif isinstance(data,dict) and isinstance(data.get('data'),list): rows=data['data']
        else: raise ConnectorError('Unexpected Analytics export structure; async-only views need an async adapter')
        return bounded([project(row,dataset['fields']) for row in rows],dataset)
