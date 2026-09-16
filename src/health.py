import importlib.util,json
from pathlib import Path
from src.config import settings
from src.database import db
from src.ollama_client import health

def check():
    result={'configuration':'valid','embedding_backend':settings.embedding_backend}
    try: db.verify();result['database']='ready'
    except Exception as exc: result['database']=type(exc).__name__
    try: result['ollama']=health()
    except Exception as exc: result['ollama']={'reachable':False,'error_type':type(exc).__name__}
    result['embedding_model_available']=settings.embedding_backend=='lexical_demo' or Path(settings.embedding_model).is_dir()
    result['dependencies']={name:importlib.util.find_spec(name) is not None for name in
        ['psycopg','sentence_transformers','pypdf','pypdfium2','docx','pptx','openpyxl','PIL','pytesseract','odf','defusedxml','bs4','fastapi']}
    import shutil
    result['tesseract_available']=shutil.which('tesseract') is not None
    from src.connectors.registry import load_catalog
    try:
        catalog=load_catalog();result['registered_sources']=sum(1 for s in catalog['sources'] if s['enabled'])
    except Exception as exc: result['connector_catalog']=type(exc).__name__
    result['documents_directory']=settings.documents.is_dir()
    return result
if __name__=='__main__': print(json.dumps(check(),indent=2))
