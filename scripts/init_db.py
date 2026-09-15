import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.database import db
if __name__=='__main__':
    db.initialize();print('EAIL tables initialized. Existing legacy RAG tables are untouched.')
