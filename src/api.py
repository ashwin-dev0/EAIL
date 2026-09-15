"""Loopback FastAPI endpoint. Place behind authenticated HTTPS for network use."""
import json, threading, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from src.auth import authenticate
from src.database import db
from src.orchestrator import ask
from src.ingestion_status import status
from src.workflows import propose,approve,list_actions
from src.logging_setup import event

@asynccontextmanager
async def lifespan(app):
    db.verify()
    from src.auth import load_users
    load_users()
    yield
app=FastAPI(title='Enterprise Agentic Intelligence Layer',version='0.1.0',lifespan=lifespan)

lock=threading.Lock();buckets={}
@app.middleware('http')
async def limits(request:Request,call_next):
    length=request.headers.get('content-length')
    try:
        if length and int(length)>65536: return JSONResponse({'detail':'Request too large'},status_code=413)
    except ValueError: return JSONResponse({'detail':'Invalid content length'},status_code=400)
    if request.method in {'POST','PUT','PATCH'}:
        # Bound actual streamed bytes, including chunked transfer requests.
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>65536: return JSONResponse({'detail':'Request too large'},status_code=413)
        request._body=bytes(body)
    # Apply the limit before authentication as well, protecting invalid-token traffic.
    key=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    with lock:
        for old in list(buckets):
            if now-buckets[old][0]>60: del buckets[old]
        timestamp,count=buckets.get(key,(now,0))
        if count>=60: return JSONResponse({'detail':'Rate limit; retry shortly'},status_code=429)
        if len(buckets)>10000: return JSONResponse({'detail':'Busy'},status_code=503)
        buckets[key]=(timestamp,count+1)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

def credentials(request:Request):
    authorization=request.headers.get('authorization','')
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    token=authorization[7:]
    try: principal=authenticate(token)
    except (PermissionError,RuntimeError): raise HTTPException(401,'Invalid credentials')
    return principal,token

class StrictModel(BaseModel): model_config=ConfigDict(extra='forbid')
class Query(StrictModel):
    question:str=Field(min_length=3,max_length=2000)
    mode:str='reasoned'
class Proposal(StrictModel):
    department:str
    title:str=Field(min_length=3,max_length=300)
    idempotency_key:str=Field(min_length=8,max_length=100)
class Scenario(StrictModel):
    department:str
    period:str
    change_percent:float=Field(ge=-100,le=100)

@app.exception_handler(PermissionError)
async def forbidden(request,exc): return JSONResponse({'detail':'Permission denied'},status_code=403)
@app.exception_handler(ValueError)
async def invalid(request,exc): return JSONResponse({'detail':str(exc)},status_code=400)
@app.exception_handler(Exception)
async def failure(request,exc):
    event('rag','api_failed',error_type=type(exc).__name__)
    return JSONResponse({'detail':'Service unavailable; check health and audit logs'},status_code=503)
@app.get('/health')
def health_public(): return {'service':'eail','status':'running'}
@app.get('/health/details')
def health_details(identity=Depends(credentials)):
    from src.health import check
    if not identity[0].ingest: raise PermissionError()
    return check()
@app.get('/me')
def me(identity=Depends(credentials)):
    user,_=identity
    return {'id':user.id,'role':user.role,'departments':user.departments,'clearance':user.clearance}
@app.post('/ask')
def question(body:Query,identity=Depends(credentials)): return ask(body.question,identity[1],body.mode)
@app.get('/ingestion/status')
def ingestion_status(identity=Depends(credentials)):
    if not identity[0].ingest: raise PermissionError()
    # The history includes filenames. Filter to the administrator's permitted scope.
    user=identity[0]
    visible={d['name'] for d in db.rows('SELECT name,metadata FROM eail_documents') if user.can_read(json.loads(d['metadata']))}
    return [r for r in status() if r['name'] in visible]
@app.get('/actions')
def actions(identity=Depends(credentials)): return list_actions(identity[0])
@app.post('/actions')
def new_action(body:Proposal,identity=Depends(credentials)): return propose(identity[0],**body.model_dump())
@app.post('/actions/{action_id}/approve')
def approve_action(action_id:str,identity=Depends(credentials)): return approve(identity[0],action_id)
@app.post('/analytics/scenario')
def scenario(body:Scenario,identity=Depends(credentials)):
    from src.mcp_gateway import MCPGateway
    import uuid
    return MCPGateway().call('budget_scenario',body.model_dump(),identity[1],str(uuid.uuid4()))
