"""Fixed read-only TallyPrime XML Collection exports. No import or arbitrary TDL."""
import calendar,ipaddress,re,urllib.parse,xml.etree.ElementTree as ET
from defusedxml import ElementTree as SafeET
from src.connectors.base import Adapter,Snapshot,secret,bounded,project,ConfigurationError,ConnectorError
from src.connectors.http import SafeHTTP

OBJECTS={
 'ledgers':('Ledger','LEDGER',['Name','GUID','Parent','OpeningBalance','ClosingBalance']),
 'vouchers':('Voucher','VOUCHER',['Date','GUID','VoucherNumber','VoucherTypeName','PartyLedgerName','Amount','IsCancelled','AllLedgerEntries.LedgerName','AllLedgerEntries.Amount','AllLedgerEntries.IsDeemedPositive']),
 'stock_items':('StockItem','STOCKITEM',['Name','GUID','Parent','BaseUnits','ClosingBalance','ClosingValue'])}
FIELDS={'NAME':'name','GUID':'guid','PARENT':'parent','OPENINGBALANCE':'opening_balance',
 'CLOSINGBALANCE':'closing_balance','DATE':'date','VOUCHERNUMBER':'voucher_number',
 'VOUCHERTYPENAME':'voucher_type','PARTYLEDGERNAME':'party_ledger','AMOUNT':'amount',
 'ISCANCELLED':'is_cancelled','BASEUNITS':'base_units','CLOSINGVALUE':'closing_value'}

def build_export(resource,company,period=None):
    if resource not in OBJECTS: raise ConfigurationError('Tally collection is not approved')
    if not company or len(company)>200: raise ConfigurationError('Exact Tally company name required')
    envelope=ET.Element('ENVELOPE');header=ET.SubElement(envelope,'HEADER')
    for tag,value in [('VERSION','1'),('TALLYREQUEST','Export'),('TYPE','Collection'),('ID','EAILReadCollection')]:
        ET.SubElement(header,tag).text=value
    desc=ET.SubElement(ET.SubElement(envelope,'BODY'),'DESC');static=ET.SubElement(desc,'STATICVARIABLES')
    ET.SubElement(static,'SVCURRENTCOMPANY').text=company
    ET.SubElement(static,'SVEXPORTFORMAT').text='$$SysName:XML'
    if resource=='vouchers':
        if not period or not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])',period): raise ConfigurationError('Voucher export requires YYYY-MM')
        year,month=map(int,period.split('-'));last=calendar.monthrange(year,month)[1]
        ET.SubElement(static,'SVFROMDATE',{'TYPE':'Date'}).text=f'{year:04d}{month:02d}01'
        ET.SubElement(static,'SVTODATE',{'TYPE':'Date'}).text=f'{year:04d}{month:02d}{last:02d}'
    messages=ET.SubElement(ET.SubElement(desc,'TDL'),'TDLMESSAGE')
    collection=ET.SubElement(messages,'COLLECTION',{'NAME':'EAILReadCollection','ISMODIFY':'No'})
    object_type,_,fetch=OBJECTS[resource]
    ET.SubElement(collection,'TYPE').text=object_type
    ET.SubElement(collection,'FETCH').text=','.join(fetch)
    if resource=='vouchers':
        ET.SubElement(collection,'FILTER').text='EAILDateRange'
        formula=ET.SubElement(messages,'SYSTEM',{'TYPE':'Formulae','NAME':'EAILDateRange'})
        formula.text='$Date >= ##SVFROMDATE AND $Date <= ##SVTODATE'
    return ET.tostring(envelope,encoding='utf-8',xml_declaration=True)

class TallyAdapter(Adapter):
    def __init__(self,source,http=None):
        self.source=source;url=secret(source['url_env']);u=urllib.parse.urlsplit(url)
        if u.hostname not in source.get('approved_hosts',[]) or u.username or u.password or u.query or u.fragment or u.path not in {'','/'}:
            raise ConfigurationError('Approve the exact private Tally host')
        try: loopback=ipaddress.ip_address(u.hostname).is_loopback
        except ValueError: loopback=u.hostname=='localhost'
        if u.scheme!='https' and not (u.scheme=='http' and loopback):
            raise ConfigurationError('Tally HTTP requires a loopback tunnel; use HTTPS for a remote gateway')
        self.url=url;self.http=http or SafeHTTP([f'{u.scheme}://{u.netloc}'])
    def fetch(self,dataset,period=None):
        company=secret(self.source['company_env'])
        payload=build_export(dataset['resource'],company,period)
        try:
            status,_,body=self.http.request('POST',self.url,headers={'Content-Type':'text/xml; charset=utf-8'},content=payload)
            if not 200<=status<300: raise ConnectorError('Tally export unavailable')
            # Reject DTD/entities rather than silently resolving external resources.
            try: tree=SafeET.fromstring(body)
            except Exception: raise ConnectorError('Invalid or unsafe Tally XML response')
            if tree.findall('.//LINEERROR') or tree.find('.//STATUS') is not None and tree.find('.//STATUS').text=='0':
                raise ConnectorError('Tally rejected the export; verify loaded company and server configuration')
            tag=OBJECTS[dataset['resource']][1]
            rows=Snapshot(dataset)
            for element in tree.iter(tag):
                row={'name':element.attrib.get('NAME')}
                for child in element:
                    if child.tag in FIELDS: row[FIELDS[child.tag]]=''.join(child.itertext()).strip()
                entries=[]
                for entry in list(element.findall('ALLLEDGERENTRIES.LIST'))+list(element.findall('LEDGERENTRIES.LIST')):
                    entries.append({'ledger_name':entry.findtext('LEDGERNAME'),'amount':entry.findtext('AMOUNT'),'is_deemed_positive':entry.findtext('ISDEEMEDPOSITIVE')})
                if entries: row['ledger_entries']=entries
                rows.append(project(row,dataset['fields']))
            # Valid empty collections are allowed only by the dataset policy at sync.
            if not rows and tree.find('.//COLLECTION') is None: raise ConnectorError('Tally did not return a collection envelope')
            return rows
        finally: self.http.close()
