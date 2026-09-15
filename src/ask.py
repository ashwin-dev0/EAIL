import getpass,json,os
from src.orchestrator import ask
from src.database import db

def main():
    db.verify();token=os.getenv('EAIL_TOKEN') or getpass.getpass('EAIL user token: ')
    print('EAIL — local enterprise intelligence. Type exit to quit. Prefix /extract for evidence excerpts.')
    while True:
        question=input('\nAsk: ').strip()
        if question.lower()=='exit': break
        mode='extractive' if question.startswith('/extract ') else 'reasoned'
        if mode=='extractive': question=question[len('/extract '):]
        try: print(json.dumps(ask(question,token,mode),indent=2,ensure_ascii=False))
        except Exception as exc: print(f'{type(exc).__name__}: request could not be completed. Check service health, permissions and audit logs.')
if __name__=='__main__': main()
