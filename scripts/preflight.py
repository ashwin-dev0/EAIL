import importlib.util,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.config import settings,ROOT
from src.auth import load_users
from src.database import db

def main():
    errors=[]
    for path in [settings.documents,settings.logs]: path.mkdir(parents=True,exist_ok=True,mode=0o700)
    try: load_users()
    except Exception as exc: errors.append('User configuration: '+type(exc).__name__)
    try: db.verify()
    except Exception as exc: errors.append('Database: '+type(exc).__name__)
    if settings.embedding_backend=='minilm':
        if not Path(settings.embedding_model).is_dir(): errors.append('Local embedding model missing')
        if not importlib.util.find_spec('sentence_transformers'): errors.append('sentence-transformers missing')
    if errors:
        print('\n'.join(errors));return 1
    print('Preflight passed. Run python -m src.health for Ollama/OCR/format dependency checks.');return 0
if __name__=='__main__': raise SystemExit(main())
