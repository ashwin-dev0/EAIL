"""MCP JSON-RPC stdio server, newline-delimited framing.
Internal process only. Opaque user credential inherited from the trusted gateway.
No network listener, model-visible secrets, shell tools, or arbitrary SQL.
"""
import json, os, sys
from src.auth import authenticate
from src.analytics import TOOLS, dispatch
MAX_MESSAGE=65536
PROTOCOLS={'2025-03-26','2025-06-18','2025-11-25'}

def run():
    initialized=False; ready=False
    for raw in sys.stdin.buffer:
        if len(raw)>MAX_MESSAGE: raise SystemExit('MCP message limit')
        request_id=None
        try:
            req=json.loads(raw);request_id=req.get('id');method=req.get('method')
            if req.get('jsonrpc')!='2.0': raise ValueError('Invalid JSON-RPC')
            if method=='initialize':
                requested=req.get('params',{}).get('protocolVersion')
                protocol=requested if requested in PROTOCOLS else '2025-06-18'
                result={'protocolVersion':protocol,'capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'eail-departments','version':'0.2.0'}}
                initialized=True
            elif method=='notifications/initialized':
                if not initialized: raise ValueError('Initialization required')
                ready=True;continue
            elif method=='ping': result={}
            elif method=='tools/list':
                if not ready: raise ValueError('Initialization required')
                result={'tools':[{'name':name,'description':v['description'],'inputSchema':v['parameters'],
                   'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}} for name,v in TOOLS.items()]}
            elif method=='tools/call':
                if not ready: raise ValueError('Initialization required')
                user=authenticate(os.environ.get('EAIL_MCP_TOKEN',''))
                params=req.get('params',{})
                try:
                    value=dispatch(params['name'],params.get('arguments',{}),user)
                    result={'content':[{'type':'text','text':json.dumps(value)}],'isError':False}
                except Exception as exc:
                    result={'content':[{'type':'text','text':type(exc).__name__}],'isError':True}
            elif method and method.startswith('notifications/'): continue
            else:
                if request_id is not None:
                    print(json.dumps({'jsonrpc':'2.0','id':request_id,'error':{'code':-32601,'message':'Method not found'}}),flush=True)
                continue
            if request_id is not None: print(json.dumps({'jsonrpc':'2.0','id':request_id,'result':result}),flush=True)
        except Exception:
            if request_id is not None:
                print(json.dumps({'jsonrpc':'2.0','id':request_id,'error':{'code':-32602,'message':'Invalid request'}}),flush=True)
if __name__=='__main__': run()
