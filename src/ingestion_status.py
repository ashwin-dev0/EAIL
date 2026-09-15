import json
from src.database import db

def status():
    return db.rows('SELECT name,state,detail,created_at FROM eail_ingestion ORDER BY created_at DESC LIMIT 100')
if __name__=='__main__': print(json.dumps(status(),indent=2))
