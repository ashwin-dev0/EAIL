import json, logging, os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from src.config import settings

def now(): return datetime.now(timezone.utc).isoformat()
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'time':now(),'level':record.levelname, **record.payload}, ensure_ascii=False)

def event(channel, event_name, **fields):
    if channel not in {'rag','audit','security','ingestion'}: raise ValueError('Unknown log channel')
    # Only explicit metadata fields should be supplied. Never log exception strings,
    # credentials, raw questions, model text, or document contents.
    logger = logging.getLogger('eail.'+channel)
    if not logger.handlers:
        settings.logs.mkdir(parents=True,exist_ok=True,mode=0o700)
        handler = RotatingFileHandler(settings.logs/(channel+'.log'),maxBytes=5_000_000,backupCount=5)
        if os.name == 'posix': os.chmod(handler.baseFilename,0o600)
        handler.setFormatter(JSONFormatter());logger.addHandler(handler)
        logger.setLevel(logging.INFO);logger.propagate=False
    logger.info('', extra={'payload':{'event':event_name, **fields}})
