"""AENIMUS FastAPI bridge v0.1.0."""
import asyncio, difflib, json, os, re
from datetime import datetime, timezone
import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .config import settings
from .db import Store
from .models import Agent, Swarm, SessionCreate, ChatRequest, FileRequest, WriteRequest, TerminalRequest, DiagnosticRequest, ApprovalDecision, MaintenanceRequest
from .orchestrator import run
from .personas import load_directory
from .providers import DEFAULT_PROVIDERS, list_models
from .security import inspect_prompt, redact, safe_path, validate_argv
from .memory import recall, remember

BASE=Path(__file__).resolve().parent
settings.workspace.mkdir(parents=True,exist_ok=True); settings.data_dir.mkdir(parents=True,exist_ok=True)
store=Store(settings.data_dir/"aenimus.db")
app=FastAPI(title="AENIMUS Agent Studio",version="0.1.0",docs_url="/api/docs")
app.mount("/assets",StaticFiles(directory=BASE/"static"),name="assets")


def seed():
    if store.agents(): return
    for p in load_directory(BASE.parent/"personas"):
        store.put_agent(Agent(**p).model_dump())
seed()

@app.get("/")
async def index(): return FileResponse(BASE/"static/index.html")
@app.get("/api/health")
async def health(): return {"status":"ok","version":"0.1.0","workspace":str(settings.workspace)}
@app.get("/api/agents")
async def agents(): return store.agents()
@app.get("/api/swarms")
async def swarms(): return store.swarms()
@app.put("/api/swarms/{swarm_id}")
async def put_swarm(swarm_id:str,swarm:Swarm):
    if swarm.id!=swarm_id: raise HTTPException(400,"Swarm ID mismatch")
    known={a["id"] for a in store.agents()}
    if any(x not in known for x in swarm.agent_ids): raise HTTPException(400,"Swarm contains unknown agent")
    if swarm.head_agent_id and swarm.head_agent_id not in swarm.agent_ids: raise HTTPException(400,"Head agent must belong to swarm")
    store.put_swarm(swarm.model_dump()); store.audit("swarm.updated","user",{"swarm_id":swarm_id}); return swarm
@app.put("/api/agents/{agent_id}")
async def put_agent(agent_id:str,agent:Agent):
    if agent.id!=agent_id: raise HTTPException(400,"Agent ID mismatch")
    store.put_agent(agent.model_dump()); store.audit("agent.updated","user",{"agent_id":agent_id}); return agent
@app.get("/api/providers")
async def providers():
    return [{"id":k,**v,"key_configured":bool(os.getenv(v["api_key_env"])) if v["api_key_env"] else True} for k,v in DEFAULT_PROVIDERS.items()]
@app.get("/api/providers/{provider}/models")
async def models(provider:str):
    try: return await list_models(provider)
    except Exception as e: raise HTTPException(502,f"Provider unavailable: {redact(e)}")
@app.get("/api/sessions")
async def sessions(): return store.sessions()
@app.post("/api/sessions")
async def create_session(req:SessionCreate):
    ids=req.agent_ids or [a["id"] for a in store.agents()]
    item=store.session(req.title,ids,req.orchestration); store.audit("session.created","user",{"session_id":item["id"]}); return item
@app.get("/api/sessions/{session_id}/messages")
async def messages(session_id:str): return store.messages(session_id)
@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id:str,req:ChatRequest):
    session=next((x for x in store.sessions() if x["id"]==session_id),None)
    if not session: raise HTTPException(404,"Session not found")
    inspection=inspect_prompt(req.content)
    user=store.message(session_id,"user",req.content,channel="main")
    await remember(session_id,req.agent_id or "shared","user",req.content)
    store.audit("prompt.received","user",{"session_id":session_id,"inspection":inspection})
    try: output=await run(store,session,req,store.agents())
    except Exception as e: raise HTTPException(502,redact(e))
    return {"user":user,"inspection":inspection,"messages":output}
@app.post("/api/inspect")
async def inspect(req:ChatRequest): return inspect_prompt(req.content)
@app.get("/api/files")
async def files(path:str="."):
    try: root=safe_path(path, must_exist=True)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(400,str(e))
    if not root.is_dir(): raise HTTPException(400,"Not a directory")
    return [{"name":x.name,"path":str(x.relative_to(settings.workspace.resolve())),"directory":x.is_dir(),"size":x.stat().st_size if x.is_file() else None} for x in sorted(root.iterdir(),key=lambda x:(not x.is_dir(),x.name.lower())) if not x.is_symlink()][:500]
@app.post("/api/files/read")
async def read_file(req:FileRequest):
    try: p=safe_path(req.path,must_exist=True)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(400,str(e))
    if not p.is_file() or p.stat().st_size>settings.max_file_bytes: raise HTTPException(400,"File is unavailable or too large")
    store.audit("file.read","user",{"path":req.path}); return {"path":req.path,"content":p.read_text(errors="replace")}
@app.post("/api/files/diff")
async def diff(req:WriteRequest):
    try: p=safe_path(req.path)
    except ValueError as e: raise HTTPException(400,str(e))
    old=p.read_text(errors="replace") if p.exists() else ""
    delta="".join(difflib.unified_diff(old.splitlines(True),req.content.splitlines(True),fromfile=f"a/{req.path}",tofile=f"b/{req.path}"))
    approval=store.approval("file.write",{"path":req.path,"content":req.content})
    store.audit("file.diff_created","user",{"path":req.path,"approval_id":approval["id"]})
    return {"diff":delta,"approval":approval}
@app.post("/api/files/apply")
async def apply(req:WriteRequest):
    if settings.require_approval and not store.consume_approval(req.approval_id or "","file.write",{"path":req.path,"content":req.content}): raise HTTPException(403,"Matching, unused approved diff required")
    try: p=safe_path(req.path)
    except ValueError as e: raise HTTPException(400,str(e))
    if len(req.content.encode())>settings.max_file_bytes: raise HTTPException(400,"File too large")
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(req.content)
    store.audit("file.written","user",{"path":req.path}); return {"ok":True}
@app.post("/api/terminal/prepare")
async def prepare_terminal(req:TerminalRequest):
    try: validate_argv(req.argv); safe_path(req.cwd,must_exist=True)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(400,str(e))
    approval=store.approval("terminal.exec",{"argv":req.argv,"cwd":req.cwd}); return approval
@app.post("/api/diagnostics/run")
async def diagnostics(req:DiagnosticRequest):
    try: target=safe_path(req.path,must_exist=True)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(400,str(e))
    relative=str(target.relative_to(settings.workspace.resolve())) or "."
    commands={
        "lint":["ruff","check","--output-format=json",relative],
        "test":["python","-m","unittest","discover","-v"],
        "debug":["python","-m","compileall","-q",relative],
    }
    proc=await asyncio.create_subprocess_exec(*commands[req.mode],cwd=settings.workspace.resolve(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env={"PATH":os.getenv("PATH","/usr/local/bin:/usr/bin:/bin"),"PYTHONFAULTHANDLER":"1","LANG":"C.UTF-8"})
    try: out,err=await asyncio.wait_for(proc.communicate(),settings.command_timeout)
    except asyncio.TimeoutError: proc.kill(); raise HTTPException(408,"Diagnostic timed out")
    result={"mode":req.mode,"path":req.path,"exit_code":proc.returncode,"stdout":redact(out.decode(errors="replace"))[-100000:],"stderr":redact(err.decode(errors="replace"))[-100000:]}
    store.audit("diagnostic.completed","system",{"mode":req.mode,"path":req.path,"exit_code":proc.returncode}); return result
@app.post("/api/terminal/run")
async def terminal(req:TerminalRequest):
    if settings.require_approval and not store.consume_approval(req.approval_id or "","terminal.exec",{"argv":req.argv,"cwd":req.cwd}): raise HTTPException(403,"Matching, unused approved command required")
    try: validate_argv(req.argv); cwd=safe_path(req.cwd,must_exist=True)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(400,str(e))
    try:
        proc=await asyncio.create_subprocess_exec(*req.argv,cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env={"PATH":os.getenv("PATH","/usr/bin:/bin"),"LANG":"C.UTF-8"})
        out,err=await asyncio.wait_for(proc.communicate(),settings.command_timeout)
    except asyncio.TimeoutError: proc.kill(); raise HTTPException(408,"Command timed out")
    result={"exit_code":proc.returncode,"stdout":redact(out.decode(errors="replace"))[-50000:],"stderr":redact(err.decode(errors="replace"))[-50000:]}
    store.audit("terminal.executed","user",{"argv":req.argv,"cwd":req.cwd,"exit_code":proc.returncode}); return result
@app.get("/api/approvals")
async def approvals(): return store.approvals()
@app.post("/api/approvals/{approval_id}")
async def decide(approval_id:str,decision:ApprovalDecision):
    if not store.get_approval(approval_id): raise HTTPException(404,"Approval not found")
    store.decide(approval_id,"approved" if decision.approved else "denied"); store.audit("approval.decided","user",{"approval_id":approval_id,"approved":decision.approved}); return {"ok":True}
@app.get("/api/audit")
async def audit(): return store.audits()

def backup_path(name:str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+",name): raise HTTPException(400,"Invalid backup name")
    return settings.data_dir/"backups"/f"{name}.db"

@app.get("/api/maintenance/backups")
async def backups():
    root=settings.data_dir/"backups"; root.mkdir(parents=True,exist_ok=True)
    return [{"name":x.stem,"bytes":x.stat().st_size,"created_at":datetime.fromtimestamp(x.stat().st_mtime,timezone.utc).isoformat()} for x in sorted(root.glob("*.db"),reverse=True)]
@app.post("/api/maintenance/backup")
async def backup(req:MaintenanceRequest):
    name=req.name or datetime.now(timezone.utc).strftime("aenimus-%Y%m%dT%H%M%SZ")
    path=backup_path(name); store.backup(path)
    qdrant=None
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.post(f"{settings.qdrant_url}/collections/aenimus_memory/snapshots"); r.raise_for_status(); qdrant=r.json().get("result",{}).get("name")
    except httpx.HTTPError: pass
    store.audit("backup.created","user",{"name":name,"qdrant_snapshot":qdrant}); return {"name":name,"qdrant_snapshot":qdrant}
@app.post("/api/maintenance/prepare")
async def prepare_maintenance(req:MaintenanceRequest):
    if req.scope=="all" and req.name is None: action="maintenance.purge"
    else: action="maintenance.restore" if req.name else "maintenance.purge"
    return store.approval(action,req.model_dump(exclude={"approval_id"}))
@app.post("/api/maintenance/restore")
async def restore(req:MaintenanceRequest):
    prepared=req.model_dump(exclude={"approval_id"})
    if not store.consume_approval(req.approval_id or "","maintenance.restore",prepared): raise HTTPException(403,"Matching, unused approved restore required")
    if not req.name: raise HTTPException(400,"Backup name required")
    path=backup_path(req.name)
    if not path.exists(): raise HTTPException(404,"Backup not found")
    store.restore(path); store.audit("backup.restored","user",{"name":req.name}); return {"ok":True,"restart_recommended":True}
@app.post("/api/maintenance/purge")
async def purge(req:MaintenanceRequest):
    prepared=req.model_dump(exclude={"approval_id"})
    if not store.consume_approval(req.approval_id or "","maintenance.purge",prepared): raise HTTPException(403,"Matching, unused approved purge required")
    if req.scope in ("history","all"): store.purge_history()
    if req.scope in ("memory","all"):
        try:
            async with httpx.AsyncClient(timeout=20) as c: await c.delete(f"{settings.qdrant_url}/collections/aenimus_memory")
        except httpx.HTTPError: pass
    store.audit("data.purged","user",{"scope":req.scope}); return {"ok":True}

@app.post("/mcp")
async def mcp(payload:dict):
    """MCP JSON-RPC surface for local automation and awake-agent controllers."""
    method=payload.get("method"); ident=payload.get("id")
    if method=="initialize":
        result={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"aenimus","version":"0.1.0"}}
    elif method=="tools/list":
        result={"tools":[
            {"name":"list_agents","description":"List configured AENIMUS agents","inputSchema":{"type":"object"}},
            {"name":"recall_memory","description":"Retrieve long-term contextual memory","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"agent_id":{"type":"string"}},"required":["query"]}},
            {"name":"wake_agent","description":"Wake an agent into a session","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"agent_id":{"type":"string"},"prompt":{"type":"string"}},"required":["session_id","agent_id","prompt"]}}
        ]}
    elif method=="tools/call":
        params=payload.get("params",{}); name=params.get("name"); args=params.get("arguments",{})
        if name=="list_agents": value=store.agents()
        elif name=="recall_memory": value=await recall(args["query"],args.get("agent_id"))
        elif name=="wake_agent":
            session=next((x for x in store.sessions() if x["id"]==args["session_id"]),None)
            if not session: raise HTTPException(404,"Session not found")
            inspection=inspect_prompt(args["prompt"])
            if inspection["risk"]=="high": raise HTTPException(403,"Wake prompt blocked by injection inspection")
            store.message(session["id"],"user",args["prompt"],channel="mcp")
            value=await run(store,session,ChatRequest(content=args["prompt"],agent_id=args["agent_id"]),store.agents())
            store.audit("agent.woken","mcp",{"session_id":session["id"],"agent_id":args["agent_id"]})
        else: raise HTTPException(404,"Unknown tool")
        result={"content":[{"type":"text","text":json.dumps(value)}]}
    else:
        return {"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Method not found"}}
    return {"jsonrpc":"2.0","id":ident,"result":result}

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app.main:app",host=settings.host,port=settings.port,reload=False)
