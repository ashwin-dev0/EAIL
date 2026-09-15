"""Single bounded reconciliation worker. No unbounded event queue."""
import signal, threading
from src.config import settings
from src.database import db
from src.ingest import reconcile
from src.logging_setup import event
stop=threading.Event()
def main():
    db.verify()
    for sig in [signal.SIGTERM,signal.SIGINT]: signal.signal(sig,lambda *_:stop.set())
    event('ingestion','watcher_started')
    while not stop.is_set():
        try: reconcile()
        except Exception as exc: event('ingestion','reconcile_error',error_type=type(exc).__name__)
        stop.wait(settings.watcher_interval)
    event('ingestion','watcher_stopped')
if __name__=='__main__': main()
