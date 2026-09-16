import json,os,sqlite3,unittest
from unittest.mock import patch
import httpx
from test_system import TMP,TOKENS,meta,users_file
from src.database import db
from src.auth import authenticate
from src.connectors.registry import load_catalog,resolve
from src.connectors.base import ConfigurationError,ConnectorError,IncompleteSnapshot,SourceUnavailable
from src.connectors.http import SafeHTTP
from src.connectors.zoho import ZohoAdapter,zoho_origins
from src.connectors.tally import TallyAdapter,build_export
from src.connectors.sync import sync_dataset
from src.connectors.query import source_records,list_datasets,snapshot_still_valid
CATALOG=TMP/'connectors.json'
def source(**changes):
 return dict(id='test-zoho',kind='zoho_books',enabled=True,region='in',organization_id='123',client_id_env='TEST_ZOHO_ID',client_secret_env='TEST_ZOHO_SECRET',refresh_token_env='TEST_ZOHO_REFRESH')|changes
def dataset(**changes):
 return dict(id='test-invoices',source_id='test-zoho',enabled=True,resource='invoices',fields=['invoice_id','date','currency_code','total','balance'],id_field='invoice_id',period_field='date',metadata=meta('Finance',allowed_roles=['CFO','Admin']),max_rows=100,max_bytes=100000,max_age_seconds=3600,allow_empty=False,sync_scope='all',measures=[dict(name='total',field='total',operation='sum_decimal',currency_field='currency_code',unit='major_currency_units')])|changes
def catalog(s=None,d=None):
 CATALOG.write_text(json.dumps({'sources':[s or source()],'datasets':[d or dataset()]}));CATALOG.chmod(0o600)
class ConnectorTests(unittest.TestCase):
 def setUp(self):
  users_file();db.initialize()
  with db.connect() as conn:
   for table in ['eail_source_records','eail_sync_runs','eail_sync_state']: db.execute(conn,'DELETE FROM '+table)
  e=patch.dict(os.environ,CONNECTORS_FILE=str(CATALOG),TEST_ZOHO_ID='id',TEST_ZOHO_SECRET='secret',TEST_ZOHO_REFRESH='refresh');e.start();self.addCleanup(e.stop);catalog()
 def rows(self):
  return [{'invoice_id':'one','date':'2026-08-01','currency_code':'INR','total':'10.01','balance':'1.00'},{'invoice_id':'two','date':'2026-08-02','currency_code':'INR','total':'20.02','balance':'2.00'}]
 def sync(self,rows=None):
  adapter=type('Fixture',(),{'fetch':lambda *_:self.rows() if rows is None else rows})()
  with patch('src.connectors.sync.create_adapter',return_value=adapter): return sync_dataset('test-invoices',isolated=False)
 def http(self,handler,origins=None,limit=100000):
  return SafeHTTP(origins or zoho_origins('in'),max_bytes=limit,client=httpx.Client(transport=httpx.MockTransport(handler)))
 def test_parent_field_projection(self):
  self.sync([self.rows()[0]|{'secret':'never publish'}])
  result=source_records(authenticate(TOKENS['cfo']),'test-invoices')
  self.assertNotIn('secret',result['records'][0]['data'])
 def test_parent_byte_limit(self):
  catalog(d=dataset(max_bytes=1000))
  with self.assertRaises(IncompleteSnapshot): self.sync([self.rows()[0]|{'balance':'x'*2000}])
 def test_approved_variance(self):
  catalog(d=dataset(measures=[dict(name='paid',operation='difference_decimal',field='total',baseline_field='balance',currency_field='currency_code',unit='major_currency_units')]))
  self.sync();result=source_records(authenticate(TOKENS['cfo']),'test-invoices')
  self.assertEqual(result['measures'][0]['by_currency']['INR'],'27.03')
 def test_acl_denial(self):
  with self.assertRaises(PermissionError): resolve('test-invoices',authenticate(TOKENS['employee']))
 def test_explicit_fields_required(self):
  catalog(d=dataset(fields=['total']))
  with self.assertRaises(ConfigurationError): load_catalog()
 def test_disabled_source_refused(self):
  catalog(s=source(enabled=False))
  with self.assertRaises(ConfigurationError): resolve('test-invoices')
 def test_unknown_driver_refused(self):
  catalog(s=source(kind='shell'))
  with self.assertRaises(ConfigurationError): load_catalog()
 def test_catalog_write_permissions(self):
  CATALOG.chmod(0o666)
  with self.assertRaises(ConfigurationError): load_catalog()
 def test_zoho_oauth_pagination(self):
  requests=[]
  def handler(req):
   requests.append(req)
   if req.url.path.endswith('/token'):
    self.assertEqual(req.url.params['grant_type'],'refresh_token');return httpx.Response(200,json={'access_token':'token','api_domain':'https://www.zohoapis.in'})
   page=req.url.params['page'];self.assertEqual(req.headers['authorization'],'Zoho-oauthtoken token');self.assertEqual(req.url.params['organization_id'],'123')
   return httpx.Response(200,json={'code':0,'invoices':[self.rows()[int(page)-1]],'page_context':{'has_more_page':page=='1'}})
  result=ZohoAdapter(source(),self.http(handler)).fetch(dataset());self.assertEqual(len(result),2)
  self.assertEqual(sum(r.url.path.endswith('/token') for r in requests),1);self.assertTrue(all('question' not in r.url.params for r in requests))
 def test_401_single_refresh(self):
  counts={'tokens':0,'reads':0}
  def handler(req):
   if req.url.path.endswith('/token'):
    counts['tokens']+=1;return httpx.Response(200,json={'access_token':f"token-{counts['tokens']}"})
   counts['reads']+=1
   return httpx.Response(401) if counts['reads']==1 else httpx.Response(200,json={'invoices':self.rows(),'page_context':{'has_more_page':False}})
  self.assertEqual(len(ZohoAdapter(source(),self.http(handler)).fetch(dataset())),2);self.assertEqual(counts['tokens'],2)
 def test_wrong_region(self):
  h=lambda _:httpx.Response(200,json={'access_token':'token','api_domain':'https://www.zohoapis.com'})
  with self.assertRaises(ConfigurationError): ZohoAdapter(source(),self.http(h)).fetch(dataset())
 def test_missing_pagination_completion(self):
  def h(req): return httpx.Response(200,json={'access_token':'token'} if req.url.path.endswith('/token') else {'invoices':self.rows()})
  with self.assertRaises(IncompleteSnapshot): ZohoAdapter(source(),self.http(h)).fetch(dataset())
 def test_row_limit_fail_closed(self):
  def h(req): return httpx.Response(200,json={'access_token':'token'} if req.url.path.endswith('/token') else {'invoices':self.rows(),'page_context':{'has_more_page':False}})
  with self.assertRaises(IncompleteSnapshot): ZohoAdapter(source(),self.http(h)).fetch(dataset(max_rows=1))
 def test_redirect_refused(self):
  http=self.http(lambda _:httpx.Response(302,headers={'location':'https://evil.example'}))
  try:
   with self.assertRaises(ConfigurationError): http.request('GET','https://www.zohoapis.in/test')
  finally: http.close()
 def test_ssrf_refused(self):
  http=self.http(lambda _:httpx.Response(200))
  try:
   with self.assertRaises(ConfigurationError): http.request('GET','http://169.254.169.254/latest/meta-data')
  finally: http.close()
 def test_response_limit(self):
  http=self.http(lambda _:httpx.Response(200,content=b'x'*100),limit=10)
  try:
   with self.assertRaises(ConnectorError): http.request('GET','https://www.zohoapis.in/test')
  finally: http.close()
 def test_crm_token_after_page_ten(self):
  pages=[]
  def h(req):
   if req.url.path.endswith('/token'): return httpx.Response(200,json={'access_token':'token'})
   pages.append(dict(req.url.params));page=len(pages)
   if page>10: self.assertNotIn('page',req.url.params);self.assertEqual(req.url.params['page_token'],'next-10')
   return httpx.Response(200,json={'data':[{'id':str(page),'Amount':'1'}],'info':{'more_records':page<11,'next_page_token':f'next-{page}'}})
  d=dataset(resource='Deals',fields=['id','Amount'],id_field='id')
  self.assertEqual(len(ZohoAdapter(source(kind='zoho_crm'),self.http(h)).fetch(d)),11)
 def test_analytics_personal_columns_excluded(self):
  def h(req):
   if req.url.path.endswith('/token'): return httpx.Response(200,json={'access_token':'token'})
   config=json.loads(req.url.params['CONFIG']);self.assertFalse(config['showPersonalCols']);self.assertFalse(config['showHiddenCols']);self.assertTrue(config['validateSystemTags']);self.assertEqual(req.headers['zanalytics-orgid'],'123')
   return httpx.Response(200,json=[{'id':'one','amount':'10','private':'excluded'}])
  rows=ZohoAdapter(source(kind='zoho_analytics'),self.http(h)).fetch(dataset(workspace_id='12',view_id='34',fields=['id','amount'],id_field='id'));self.assertNotIn('private',rows[0])
 def test_canadian_analytics_domain(self): self.assertEqual(zoho_origins('ca')[2],'https://analyticsapi.zohocloud.ca')
 def test_tally_export_escaped_company(self):
  xml=build_export('vouchers','Company <A>','2026-08').decode();self.assertIn('<TALLYREQUEST>Export</TALLYREQUEST>',xml);self.assertNotIn('Import',xml);self.assertIn('Company &lt;A&gt;',xml);self.assertIn('20260831',xml)
 def test_tally_company_required(self):
  with self.assertRaises(ConfigurationError): build_export('ledgers','')
 def test_tally_remote_cleartext_refused(self):
  with patch.dict(os.environ,TALLY_TEST_URL='http://192.168.1.1:9000'):
   with self.assertRaises(ConfigurationError): TallyAdapter(dict(url_env='TALLY_TEST_URL',approved_hosts=['192.168.1.1']))
 def tally(self,body):
  def h(req): self.assertIn(b'<TALLYREQUEST>Export</TALLYREQUEST>',req.content);return httpx.Response(200,content=body)
  with patch.dict(os.environ,TALLY_TEST_URL='http://127.0.0.1:9000',TALLY_TEST_COMPANY='Company'):
   s=dict(kind='tally',url_env='TALLY_TEST_URL',company_env='TALLY_TEST_COMPANY',approved_hosts=['127.0.0.1'])
   return TallyAdapter(s,self.http(h,['http://127.0.0.1:9000'])).fetch(dataset(resource='ledgers',fields=['guid','name','closing_balance'],id_field='guid'))
 def test_tally_xml_balance_preserved(self):
  rows=self.tally(b'<ENVELOPE><BODY><COLLECTION><LEDGER NAME="Cash"><GUID>one</GUID><CLOSINGBALANCE>-100.50</CLOSINGBALANCE></LEDGER></COLLECTION></BODY></ENVELOPE>');self.assertEqual(rows[0]['closing_balance'],'-100.50');self.assertEqual(rows[0]['name'],'Cash')
 def test_tally_entities_refused(self):
  with self.assertRaises(ConnectorError): self.tally(b'<!DOCTYPE x [<!ENTITY s SYSTEM "file:///etc/passwd">]><ENVELOPE>&s;</ENVELOPE>')
 def test_tally_error_refused(self):
  with self.assertRaises(ConnectorError): self.tally(b'<ENVELOPE><LINEERROR>Unavailable company</LINEERROR></ENVELOPE>')
 def test_atomic_decimal_snapshot(self):
  self.sync();r=source_records(authenticate(TOKENS['cfo']),'test-invoices','2026-08');self.assertEqual(r['measures'][0]['by_currency']['INR'],'30.03');self.assertEqual(r['matching_records'],2)
 def test_duplicate_ids_preserve_previous_snapshot(self):
  self.sync();old=db.rows('SELECT generation FROM eail_sync_state')[0]['generation']
  with self.assertRaises(ConnectorError): self.sync([self.rows()[0],self.rows()[0]])
  self.assertEqual(db.rows('SELECT generation FROM eail_sync_state')[0]['generation'],old);self.assertTrue(source_records(authenticate(TOKENS['cfo']),'test-invoices')['warnings'])
 def test_empty_snapshot_refused(self):
  with self.assertRaises(IncompleteSnapshot): self.sync([])
 def test_policy_change_invalidates_immediately(self):
  self.sync();r=source_records(authenticate(TOKENS['cfo']),'test-invoices');catalog(d=dataset(metadata=meta('Finance',allowed_users=['admin'])));self.assertFalse(snapshot_still_valid(r,authenticate(TOKENS['cfo'])))
 def test_secret_rotation_invalidates(self):
  self.sync()
  with patch.dict(os.environ,TEST_ZOHO_REFRESH='rotated'):
   with self.assertRaises(SourceUnavailable): source_records(authenticate(TOKENS['cfo']),'test-invoices')
 def test_stale_snapshot_refused(self):
  self.sync()
  with db.connect() as conn: db.execute(conn,"UPDATE eail_sync_state SET synced_at='2000-01-01T00:00:00+00:00'")
  with self.assertRaises(SourceUnavailable): source_records(authenticate(TOKENS['cfo']),'test-invoices')
 def test_row_acl_restrictions(self):
  catalog(d=dataset(fields=dataset()['fields']+['users'],row_acl={'allowed_users_field':'users'},measures=[]));self.sync([dict(self.rows()[0],users=['admin']),dict(self.rows()[1],users=['cfo'])]);self.assertEqual(source_records(authenticate(TOKENS['cfo']),'test-invoices')['matching_records'],1)
 def test_missing_row_acl_fails_closed(self):
  catalog(d=dataset(fields=dataset()['fields']+['users'],row_acl={'allowed_users_field':'users'}))
  with self.assertRaises(ConnectorError): self.sync()
 def test_mixed_currency_groups(self):
  rows=self.rows();rows[1]['currency_code']='USD';self.sync(rows);self.assertEqual(source_records(authenticate(TOKENS['cfo']),'test-invoices')['measures'][0]['by_currency'],{'INR':'10.01','USD':'20.02'})
 def test_no_guessed_dr_cr_conversion(self):
  rows=self.rows();rows[0]['total']='100 Dr';self.sync(rows)
  with self.assertRaises(SourceUnavailable): source_records(authenticate(TOKENS['cfo']),'test-invoices')
 def test_discovery_filters_denied_datasets(self): self.assertFalse(list_datasets(authenticate(TOKENS['employee'])))
 def test_sqlite_source_real_query(self):
  from src.connectors.sql import SQLAdapter
  path=TMP/'source.db'
  with sqlite3.connect(path) as c:
   c.execute('CREATE TABLE IF NOT EXISTS approved_budget_view(id TEXT,period TEXT,category TEXT,currency TEXT,budget_minor INTEGER,actual_minor INTEGER)');c.execute('DELETE FROM approved_budget_view');c.execute('INSERT INTO approved_budget_view VALUES (?,?,?,?,?,?)',('1','2026-08','Software','INR',10000,11000))
  s=dict(id='test-sql',kind='sql',enabled=True,url_env='SQLITE_SOURCE_TEST_URL',readonly_credentials_confirmed=True,approved_files=[str(path)])
  d=dataset(source_id='test-sql',query_file='config/sql/budget.sql',fields=['id','period','category','currency','budget_minor','actual_minor'],id_field='id',measures=[])
  with patch.dict(os.environ,SQLITE_SOURCE_TEST_URL='sqlite:///'+str(path)): self.assertEqual(SQLAdapter(s).fetch(d,'2026-08')[0]['actual_minor'],11000)
 def test_sql_writes_cte_into_wildcard_refused(self):
  from src.connectors.sql import check_select
  for q in ['DELETE FROM t','SELECT * FROM t','SELECT id INTO other FROM t','WITH bad AS (DELETE FROM t RETURNING id) SELECT id FROM bad','SELECT id FROM t; DROP TABLE t']:
   with self.assertRaises(ConfigurationError,msg=q): check_select(q,'postgresql')
 def test_mcp_source_roundtrip(self):
  self.sync();from src.mcp_gateway import MCPGateway
  r=MCPGateway().call('source_records',dict(dataset_id='test-invoices',period='2026-08',limit=10),TOKENS['cfo'],'test');self.assertEqual(r['matching_records'],2)
 def test_api_source_access(self):
  from fastapi.testclient import TestClient
  from src.api import app
  self.sync()
  with TestClient(app) as c:
   h={'Authorization':'Bearer '+TOKENS['cfo']};self.assertEqual(c.get('/sources',headers=h).json()[0]['id'],'test-invoices');self.assertEqual(c.get('/sources/test-invoices/records',headers=h).status_code,200)
   self.assertEqual(c.get('/sources/test-invoices/records',headers={'Authorization':'Bearer '+TOKENS['employee']}).status_code,403)
 def test_source_answer_fallback_retains_approved_totals(self):
  self.sync();from src.orchestrator import ask
  with patch('src.orchestrator.chat',return_value=json.dumps(dict(answer='',citation_ids=[],not_found=True))): r=ask('What is the invoice total 2026-08?',TOKENS['cfo'],dataset_id='test-invoices')
  self.assertIn('30.03',r['answer']);self.assertTrue(r['citations'])
 def test_encrypted_oauth_cache_reused_across_adapters(self):
  from cryptography.fernet import Fernet
  cache=TMP/'oauth-cache.enc'
  if cache.exists(): cache.unlink()
  count={'tokens':0}
  def h(req):
   if req.url.path.endswith('/token'):
    count['tokens']+=1;return httpx.Response(200,json={'access_token':'cache-private-token','expires_in':3600})
   return httpx.Response(200,json={'invoices':self.rows(),'page_context':{'has_more_page':False}})
  s=source(token_cache_key_env='TEST_CACHE_KEY')
  with patch.dict(os.environ,TEST_CACHE_KEY=Fernet.generate_key().decode(),ZOHO_TOKEN_CACHE_FILE=str(cache)):
   for _ in range(2): ZohoAdapter(s,self.http(h)).fetch(dataset())
   self.assertEqual(count['tokens'],1);self.assertNotIn(b'cache-private-token',cache.read_bytes());self.assertEqual(cache.stat().st_mode & 0o777,0o600)
if __name__=='__main__': unittest.main()
