import hashlib, math, re, threading
from src.config import settings
_model=None
_lock=threading.Lock()

def embedding_id():
    return settings.embedding_backend+':'+settings.embedding_model if settings.embedding_backend=='minilm' else 'lexical_demo:sha256-384-v1'
def words(text): return re.findall(r"[\w]+",text.lower())
def normalize(vector):
    length=math.sqrt(sum(x*x for x in vector))
    return [x/length for x in vector] if length else vector

def encode(texts):
    global _model
    if settings.embedding_backend=='lexical_demo':
        # Explicit offline test/demo mode; NOT semantic embeddings.
        result=[]
        for text in texts:
            v=[0.0]*384
            for token in words(text):
                h=int.from_bytes(hashlib.sha256(token.encode()).digest()[:4],'big')
                v[h%384]+=1
            result.append(normalize(v))
        return result
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model=SentenceTransformer(settings.embedding_model, local_files_only=True, device='cpu')
        return _model.encode(texts,normalize_embeddings=True,batch_size=16,show_progress_bar=False).tolist()

def cosine(a,b):
    if len(a)!=len(b): raise ValueError('Embedding dimension mismatch; reingest required')
    return sum(x*y for x,y in zip(a,b))
