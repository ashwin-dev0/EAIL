import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.connectors.sync import sync_dataset
from src.connectors.registry import load_catalog

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset');parser.add_argument('--period');args=parser.parse_args()
    selected=[args.dataset] if args.dataset else [d['id'] for d in load_catalog()['datasets'] if d['enabled']]
    failed=False
    for dataset_id in selected:
        try: print(json.dumps(sync_dataset(dataset_id,args.period)))
        except Exception as exc: failed=True;print(json.dumps({'dataset_id':dataset_id,'status':'failed','error_type':type(exc).__name__}))
    return 1 if failed else 0
if __name__=='__main__': raise SystemExit(main())
