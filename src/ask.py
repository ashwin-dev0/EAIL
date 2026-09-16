import getpass,json,os
from src.orchestrator import ask
from src.database import db

def main():
    db.verify();token=os.getenv('EAIL_TOKEN') or getpass.getpass('EAIL user token: ')
    print('EAIL — local enterprise intelligence. Type exit to quit. Prefix /extract for evidence excerpts.')
    while True:
        question=input('\nAsk: ').strip()
        dataset_id=None
        if question.startswith('/source '):
            parts=question.split(' ',2)
            if len(parts)!=3:
                print('Use /source DATASET_ID your question');continue
            _,dataset_id,question=parts
        if question.lower()=='exit': break
        mode='extractive' if question.startswith('/extract ') else 'reasoned'
        if mode=='extractive': question=question[len('/extract '):]
        try: print(json.dumps(ask(question,token,mode,dataset_id),indent=2,ensure_ascii=False))
        except Exception as exc: print(f'{type(exc).__name__}: request could not be completed. Check service health, permissions and audit logs.')
if __name__=='__main__': main()
