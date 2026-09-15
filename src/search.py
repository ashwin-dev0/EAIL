import hashlib, json
from src.database import db
from src.config import settings
from src.file_safety import snapshot
from src.embeddings import encode, embedding_id, cosine, words
from src.guardrails.checks import injection
from src.logging_setup import event

def search_chunks(question,principal,request_id='cli'):
    permitted=[]; stale=0
    # Read active metadata first; do not load denied chunk text into retrieval/model context.
    for document in db.rows('SELECT * FROM eail_documents WHERE active=1'):
        try:
            _,data,current_meta=snapshot(document['name'])
            if current_meta!=json.loads(document['metadata']) or hashlib.sha256(data).hexdigest()!=document['content_hash']:
                stale+=1;continue
            if not principal.can_read(current_meta): continue
            if document['embedding_id']!=embedding_id(): stale+=1;continue
            permitted.append(document)
        except Exception: stale+=1
    if not permitted: return [],{'stale_documents':stale,'blocked_chunks':0}
    query_vector=encode([question])[0];query_words=set(words(question)); results=[];blocked=0
    for document in permitted:
        for chunk in db.rows('SELECT * FROM eail_chunks WHERE document_id=?',(document['id'],)):
            if injection(chunk['content']): blocked+=1;continue
            similarity=cosine(query_vector,json.loads(chunk['embedding']))
            keyword=len(query_words & set(words(chunk['content'])))/max(len(query_words),1)
            score=.8*similarity+.2*keyword
            if similarity<settings.min_score and keyword<.5: continue
            results.append({'id':chunk['id'],'document_id':document['id'],'name':document['name'],
                'version':document['version'],'content_hash':document['content_hash'],
                'metadata':json.loads(document['metadata']),'section':chunk['section'],
                'chunk_index':chunk['chunk_index'],'score':round(score,4),'content':chunk['content'],
                'updated_at':document['updated_at']})
            if len(results)>settings.top_k*3:
                results.sort(key=lambda x:x['score'],reverse=True)
                results=results[:settings.top_k]
    results.sort(key=lambda x:x['score'],reverse=True)
    event('audit','retrieval',request_id=request_id,permitted_documents=len(permitted),
          returned_chunks=min(settings.top_k,len(results)),blocked_chunks=blocked,stale_documents=stale)
    return results[:settings.top_k],{'stale_documents':stale,'blocked_chunks':blocked}

def evidence_still_valid(sources,principal):
    checked=set()
    for source in sources:
        if source['document_id'] in checked: continue
        checked.add(source['document_id'])
        try:
            _,data,meta=snapshot(source['name'])
            if not principal.can_read(meta) or meta!=source['metadata'] or hashlib.sha256(data).hexdigest()!=source['content_hash']:
                return False
        except Exception: return False
    return True
