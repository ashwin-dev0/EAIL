import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
# Minimal .env reader: no variable interpolation or shell evaluation.
def load_env():
    file = ROOT / '.env'
    if not file.exists(): return
    if os.name == 'posix' and file.stat().st_mode & 0o077:
        raise RuntimeError('.env must have mode 600')
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_','').isalnum():
            raise RuntimeError('Invalid .env entry')
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))
load_env()
@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT/'data/eail.db'))
    documents: Path = Path(os.getenv('DOCUMENTS_DIR', str(ROOT/'documents')))
    logs: Path = Path(os.getenv('LOG_DIR', str(ROOT/'logs')))
    users: Path = Path(os.getenv('USERS_FILE', str(ROOT/'config/users.json')))
    embedding_backend: str = os.getenv('EMBEDDING_BACKEND', 'minilm')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', str(ROOT/'models/all-MiniLM-L6-v2'))
    ollama_url: str = os.getenv('OLLAMA_URL','http://127.0.0.1:11434')
    generator: str = os.getenv('OLLAMA_MODEL','llama3.2:3b')
    judge: str = os.getenv('JUDGE_MODEL','qwen2.5:1.5b')
    top_k: int = int(os.getenv('TOP_K','10'))
    min_score: float = float(os.getenv('MIN_SIMILARITY_SCORE','0.30'))
    chunk_size: int = int(os.getenv('CHUNK_SIZE','1000'))
    overlap: int = int(os.getenv('CHUNK_OVERLAP','200'))
    max_file_bytes: int = int(os.getenv('MAX_FILE_BYTES','20971520'))
    max_text: int = int(os.getenv('MAX_EXTRACTED_CHARS','2000000'))
    max_sections: int = int(os.getenv('MAX_SECTIONS','300'))
    max_rows: int = int(os.getenv('MAX_ROWS','10000'))
    extraction_timeout: int = int(os.getenv('EXTRACTION_TIMEOUT','120'))
    ocr_timeout: int = int(os.getenv('OCR_TIMEOUT','30'))
    ollama_timeout: int = int(os.getenv('OLLAMA_TIMEOUT','180'))
    keep_alive: str = os.getenv('OLLAMA_KEEP_ALIVE','5m')
    context_chars: int = int(os.getenv('MAX_CONTEXT_CHARS','9000'))
    query_timeout: int = int(os.getenv('QUERY_TIMEOUT','420'))
    watcher_interval: int = int(os.getenv('WATCHER_INTERVAL','15'))
    extraction_memory_mb: int = int(os.getenv('EXTRACTION_MEMORY_MB','2048'))
    unload_before_judge: bool = os.getenv('UNLOAD_BEFORE_JUDGE','true').lower() == 'true'
    def validate(self):
        u = urlsplit(self.ollama_url)
        if u.scheme != 'http' or u.hostname not in {'127.0.0.1','localhost','::1'} or u.username or u.password or u.path not in {'','/'}:
            raise ValueError('This release permits loopback HTTP Ollama only')
        for model in [self.generator,self.judge]:
            if 'cloud' in model.lower() or ':' not in model:
                raise ValueError('Configure explicit local Ollama model tags')
        if self.generator == self.judge: raise ValueError('Generator and judge must be separate models')
        if not 0 <= self.overlap < self.chunk_size: raise ValueError('Invalid chunk overlap')
        if not 1 <= self.top_k <= 50: raise ValueError('TOP_K must be 1..50')
        if self.embedding_backend not in {'minilm','lexical_demo'}: raise ValueError('Invalid embedding backend')
        if not 0 <= self.min_score <= 1: raise ValueError('Invalid similarity threshold')
        if self.query_timeout < 1 or self.max_file_bytes < 1: raise ValueError('Invalid resource limits')
        if self.database_url.startswith(('postgresql://','postgres://')):
            db = urlsplit(self.database_url)
            if db.username in {'postgres','root'}: raise ValueError('Use a least-privilege application DB role')
            if db.hostname not in {'localhost','127.0.0.1','::1'} and 'sslmode=verify-full' not in db.query:
                raise ValueError('Remote database requires sslmode=verify-full')
        elif not self.database_url.startswith('sqlite:///'): raise ValueError('Unsupported database URL')
        return self
settings = Settings().validate()
