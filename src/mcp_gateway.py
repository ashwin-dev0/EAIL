import json, os, subprocess, sys, time
from src.config import ROOT
from src.auth import authenticate
from src.analytics import TOOLS, validate_period,authorize_tool
from src.logging_setup import event

class MCPGateway:
    def call(self,name,args,token,request_id,timeout=20):
        principal=authenticate(token)
        if name not in TOOLS or set(args)!=set(TOOLS[name]['parameters']['required']): raise ValueError('Invalid tool call')
        authorize_tool(name,args,principal)
        env=os.environ.copy();env['EAIL_MCP_TOKEN']=token
        # Command is fixed developer code; model/user cannot select a process or module.
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'eail-host','version':'0.1.0'}}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args}}]
        begin=time.monotonic()
        result=subprocess.run([sys.executable,'-m','src.mcp_server'],input=''.join(json.dumps(m)+'\n' for m in messages),
            capture_output=True,text=True,cwd=ROOT,env=env,timeout=timeout,check=False)
        if result.returncode or len(result.stdout)>2_000_000: raise RuntimeError('MCP server failed')
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        init=next((r for r in replies if r.get('id')==1),{})
        if init.get('result',{}).get('protocolVersion')!='2025-06-18': raise RuntimeError('MCP negotiation failed')
        reply=next((r for r in replies if r.get('id')==2),{})
        data=reply.get('result',{})
        if 'error' in reply or data.get('isError',True): raise RuntimeError('Department tool failed')
        value=json.loads(data['content'][0]['text'])
        event('audit','mcp_call',request_id=request_id,user_id=principal.id,tool=name,
              department=args.get('department'),dataset_id=args.get('dataset_id'),seconds=round(time.monotonic()-begin,3))
        return value
