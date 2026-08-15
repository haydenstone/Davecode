"""AENIMUS Qdrant RAG memory adapter v0.1.0."""
import hashlib
import httpx
from .config import settings

COLLECTION="aenimus_memory"

async def _embedding(text: str):
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(settings.ollama_url.rstrip("/")+"/api/embeddings",json={"model":settings.embedding_model,"prompt":text[:12000]})
        r.raise_for_status(); return r.json()["embedding"]

async def ensure_collection(vector_size: int):
    async with httpx.AsyncClient(timeout=10) as c:
        exists=await c.get(f"{settings.qdrant_url}/collections/{COLLECTION}")
        if exists.status_code==404:
            r=await c.put(f"{settings.qdrant_url}/collections/{COLLECTION}",json={"vectors":{"size":vector_size,"distance":"Cosine"}}); r.raise_for_status()

async def remember(session_id, agent_id, role, content):
    try:
        vector=await _embedding(content); await ensure_collection(len(vector))
        point_id=int(hashlib.sha256(f"{session_id}:{agent_id}:{role}:{content}".encode()).hexdigest()[:15],16)
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.put(f"{settings.qdrant_url}/collections/{COLLECTION}/points?wait=true",json={"points":[{"id":point_id,"vector":vector,"payload":{"session_id":session_id,"agent_id":agent_id,"role":role,"content":content}}]}); r.raise_for_status()
        return True
    except (httpx.HTTPError,KeyError,ValueError): return False

async def recall(query, agent_id=None, limit=5):
    try:
        vector=await _embedding(query); body={"vector":vector,"limit":limit,"with_payload":True}
        if agent_id: body["filter"]={"must":[{"key":"agent_id","match":{"value":agent_id}}]}
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.post(f"{settings.qdrant_url}/collections/{COLLECTION}/points/search",json=body); r.raise_for_status()
        return [{"score":x["score"],**x["payload"]} for x in r.json()["result"]]
    except (httpx.HTTPError,KeyError,ValueError): return []
