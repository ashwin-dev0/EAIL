import os,signal,threading
from src.connectors.registry import load_catalog
from src.connectors.sync import sync_dataset
from src.logging_setup import event
stop=threading.Event()
def main():
    for sig in [signal.SIGTERM,signal.SIGINT]: signal.signal(sig,lambda *_:stop.set())
    while not stop.is_set():
        try:
            catalog=load_catalog();enabled={s['id'] for s in catalog['sources'] if s['enabled']}
            for dataset in catalog['datasets']:
                if stop.is_set(): break
                if not dataset['enabled'] or dataset['source_id'] not in enabled: continue
                periods=dataset.get('sync_periods',[]) if dataset.get('sync_scope','all')=='period' else [None]
                for period in periods:
                    try: sync_dataset(dataset['id'],period)
                    except Exception as exc: event('ingestion','scheduled_source_error',dataset_id=dataset['id'],error_type=type(exc).__name__)
        except Exception as exc: event('ingestion','source_catalog_error',error_type=type(exc).__name__)
        stop.wait(max(60,int(os.getenv('SOURCE_SYNC_INTERVAL','900'))))
if __name__=='__main__': main()
