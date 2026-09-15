"""Administrator model provisioning. Runtime never downloads models."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.config import settings

def main():
    from sentence_transformers import SentenceTransformer
    p=argparse.ArgumentParser();p.add_argument('--source',default='sentence-transformers/all-MiniLM-L6-v2')
    p.add_argument('--allow-download',action='store_true',help='Explicit connected-staging provisioning only')
    a=p.parse_args()
    model=SentenceTransformer(a.source,local_files_only=not a.allow_download,device='cpu')
    model.save(settings.embedding_model)
    print('Local embedding model saved. Runtime uses local_files_only=True. Treat model directory as immutable.')
if __name__=='__main__': main()
