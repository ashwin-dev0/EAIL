import json, urllib.request, time
from src.config import settings
from src.logging_setup import event
# Disable environment proxies, including proxy routing of loopback requests.
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def post(path,payload,timeout=None):
    req=urllib.request.Request(settings.ollama_url.rstrip('/')+path,json.dumps(payload).encode(),
                               {'Content-Type':'application/json'},method='POST')
    with opener.open(req,timeout=timeout or settings.ollama_timeout) as response:
        data=response.read(2_000_001)
        if len(data)>2_000_000: raise ValueError('Ollama response limit')
        return json.loads(data)

def chat(model,messages,schema=None,request_id='cli',timeout=None):
    start=time.monotonic()
    payload={'model':model,'messages':messages,'stream':False,'keep_alive':settings.keep_alive,
             'options':{'temperature':0.1,'num_predict':350,'num_ctx':4096,'num_thread':2}}
    if schema: payload['format']=schema
    result=post('/api/chat',payload,timeout)
    event('audit','ollama',request_id=request_id,model=model,seconds=round(time.monotonic()-start,3),
          load_seconds=result.get('load_duration',0)/1e9,prompt_seconds=result.get('prompt_eval_duration',0)/1e9,
          generation_seconds=result.get('eval_duration',0)/1e9,prompt_tokens=result.get('prompt_eval_count',0),
          generated_tokens=result.get('eval_count',0))
    return result['message']['content']

def unload(model): post('/api/generate',{'model':model,'keep_alive':0},timeout=15)

def health():
    with opener.open(settings.ollama_url.rstrip('/')+'/api/tags',timeout=5) as r:
        models=json.loads(r.read(1_000_000)).get('models',[])
    installed={m['name'] for m in models}
    return {'reachable':True,'generator_installed':settings.generator in installed,'judge_installed':settings.judge in installed}
