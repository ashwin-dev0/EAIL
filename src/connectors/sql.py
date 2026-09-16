"""Generic read-only SQLAlchemy source adapters plus MongoDB."""
import ipaddress,json,time
from pathlib import Path
from src.config import ROOT
from src.connectors.base import Adapter,Snapshot,secret,project,bounded,ConfigurationError,IncompleteSnapshot,SourceUnavailable
DRIVERS={'postgresql+psycopg','mysql+pymysql','mariadb+pymysql','mssql+pyodbc','oracle+oracledb','sqlite'}
DIALECT={'postgresql':'postgres','mysql':'mysql','mariadb':'mysql','mssql':'tsql','oracle':'oracle','sqlite':'sqlite'}

def check_select(query,dialect):
    import sqlglot
    from sqlglot import exp
    try: statements=sqlglot.parse(query,read=DIALECT[dialect])
    except Exception: raise ConfigurationError('Source query could not be parsed')
    if len(statements)!=1 or not isinstance(statements[0],(exp.Select,exp.Union)):
        raise ConfigurationError('Only one reviewed SELECT query is permitted')
    forbidden=(exp.Insert,exp.Update,exp.Delete,exp.Create,exp.Drop,exp.Alter,exp.Command,exp.Into,exp.Lock)
    if any(isinstance(node,forbidden) for node in statements[0].walk()): raise ConfigurationError('Source writes and locks are refused')
    if any(isinstance(node,exp.Star) for node in statements[0].walk()): raise ConfigurationError('Select explicit approved source fields')
    return query

class SQLAdapter(Adapter):
    def __init__(self,source): self.source=source
    def fetch(self,dataset,period=None):
        from sqlalchemy import create_engine,text
        from sqlalchemy.engine import make_url
        if not self.source.get('readonly_credentials_confirmed'): raise ConfigurationError('Read-only credentials required')
        uri=secret(self.source['url_env']);url=make_url(uri)
        if url.drivername not in DRIVERS: raise ConfigurationError('Install/register the approved SQL source driver')
        dialect=url.drivername.split('+')[0]
        if dialect=='sqlite':
            path=Path(url.database).resolve()
            approved={Path(p).resolve() for p in self.source.get('approved_files',[])}
            if path not in approved or not path.is_file(): raise ConfigurationError('Approve the exact source SQLite file')
        elif url.host not in self.source.get('approved_hosts',[]): raise ConfigurationError('Source DB host not approved')
        options={};query=url.query
        if dialect in {'postgresql'}:
            if query.get('sslmode')!='verify-full' and not self.source.get('loopback_development'):
                raise ConfigurationError('PostgreSQL source requires verified TLS')
            options={'connect_timeout':5}
        elif dialect in {'mysql','mariadb'}:
            ca=self.source.get('tls_ca_file')
            if not ca and not self.source.get('loopback_development'): raise ConfigurationError('MySQL/MariaDB source requires verified TLS CA')
            options={'connect_timeout':5,'read_timeout':15,'write_timeout':15}
            if ca: options['ssl']={'ca':ca,'check_hostname':True}
        elif dialect=='mssql':
            if str(query.get('Encrypt','')).lower() not in {'yes','true','mandatory'} or str(query.get('TrustServerCertificate','')).lower() not in {'no','false'}:
                raise ConfigurationError('SQL Server requires verified encrypted ODBC transport')
            options={'timeout':5}
        elif dialect=='oracle':
            # Oracle secure connect descriptor/wallet is configured by the DBA.
            if not self.source.get('verified_tcps_configured') or query.get('protocol')!='tcps' or str(query.get('ssl_server_dn_match','')).lower() not in {'true','yes'}: raise ConfigurationError('Oracle verified TCPS/wallet required')
            options={'tcp_connect_timeout':5}
        if self.source.get('loopback_development') and dialect!='sqlite':
            try: allowed=ipaddress.ip_address(url.host).is_loopback
            except ValueError: allowed=url.host=='localhost'
            if not allowed: raise ConfigurationError('Development TLS exception is loopback only')
        file=(ROOT/dataset['query_file']).resolve()
        query_root=(ROOT/'config/sql').resolve()
        if not file.is_relative_to(query_root) or not file.is_file() or file.is_symlink(): raise ConfigurationError('Queries must be reviewed files under config/sql')
        statement=check_select(file.read_text(),dialect)
        engine=create_engine(uri,connect_args=options,pool_pre_ping=True,pool_size=1,max_overflow=0) if dialect!='sqlite' else create_engine(uri)
        try:
            with engine.connect() as conn:
                if dialect=='postgresql':
                    conn.exec_driver_sql('SET TRANSACTION READ ONLY')
                    conn.exec_driver_sql("SET LOCAL statement_timeout='15000ms'")
                    conn.exec_driver_sql("SET LOCAL lock_timeout='3000ms'")
                elif dialect in {'mysql','mariadb'}: conn.exec_driver_sql('START TRANSACTION READ ONLY')
                elif dialect=='sqlite': conn.exec_driver_sql('PRAGMA query_only=ON')
                elif dialect=='oracle': conn.exec_driver_sql('SET TRANSACTION READ ONLY')
                elif dialect=='mssql': conn.connection.driver_connection.timeout=15
                cursor=conn.execution_options(stream_results=True).execute(text(statement),{'period':period})
                rows=Snapshot(dataset);start=time.monotonic()
                for row in cursor.mappings():
                    if time.monotonic()-start>20: raise SourceUnavailable('Source query deadline exceeded')
                    if not set(dataset['fields'])<=set(row.keys()): raise ConfigurationError('Query did not return approved projected fields')
                    rows.append(project(dict(row),dataset['fields']))
                return rows
        except (ConfigurationError,IncompleteSnapshot,SourceUnavailable): raise
        except Exception: raise SourceUnavailable('Database source read failed; inspect private DBA diagnostics')
        finally: engine.dispose()

class MongoAdapter(Adapter):
    def __init__(self,source): self.source=source
    def fetch(self,dataset,period=None):
        from pymongo import MongoClient
        from pymongo.uri_parser import parse_uri
        if not self.source.get('readonly_credentials_confirmed'): raise ConfigurationError('MongoDB read-only account required')
        uri=secret(self.source['url_env']);parsed=parse_uri(uri)
        if any(host not in self.source.get('approved_hosts',[]) for host,_ in parsed['nodelist']):
            raise ConfigurationError('MongoDB seed host is not approved')
        options={k.lower():v for k,v in parsed['options'].items()}
        if not options.get('tls') or options.get('tlsallowinvalidcertificates') or options.get('tlsallowinvalidhostnames'):
            raise ConfigurationError('MongoDB requires verified TLS')
        if not isinstance(dataset.get('filter',{}),dict): raise ConfigurationError('MongoDB filter must be administrator-defined')
        client=MongoClient(uri,serverSelectionTimeoutMS=5000,connectTimeoutMS=5000,socketTimeoutMS=15000)
        try:
            collection=client[dataset['database']][dataset['collection']]
            projection={f:1 for f in dataset['fields']}
            if '_id' not in projection: projection['_id']=0
            cursor=collection.find(dataset.get('filter',{}),projection).max_time_ms(15000).limit(dataset['max_rows']+1)
            return bounded([project(row,dataset['fields']) for row in cursor],dataset)
        except (ConfigurationError,IncompleteSnapshot): raise
        except Exception: raise SourceUnavailable('MongoDB source read failed')
        finally: client.close()
