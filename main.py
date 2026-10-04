import os, json, base64, uuid, math
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI(title="World AI Size Map")
app.mount("/static", StaticFiles(directory="static"), name="static")

MONGODB_URI = os.getenv("MONGODB_URI", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CF_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/black-forest-labs/flux-1-schnell")

mongo = AsyncIOMotorClient(MONGODB_URI) if MONGODB_URI else None
db = mongo["world_ai_size_map"] if mongo else None
maps = db["maps"] if db else None

class State(BaseModel):
    objects: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=lambda: {"ai_images": True})
    globe_label: str = ""

class ImageRequest(BaseModel):
    prompt: str

async def get_session(request: Request) -> str:
    sid = request.cookies.get("world_map_session")
    if not sid:
        sid = uuid.uuid4().hex
    return sid

@app.get("/")
async def index():
    return FileResponse("index.html")

@app.get("/api/health")
async def health():
    return {"ok": True, "mongodb": bool(mongo), "groq": bool(GROQ_API_KEY), "cloudflare": bool(CF_ACCOUNT_ID and CF_TOKEN)}

@app.get("/api/state")
async def get_state(request: Request):
    sid = await get_session(request)
    state = await maps.find_one({"session": sid}, {"_id": 0}) if maps else None
    response = JSONResponse(state or State().model_dump())
    if not request.cookies.get("world_map_session"):
        response.set_cookie("world_map_session", sid, max_age=31536000, httponly=True, samesite="lax")
    return response

@app.put("/api/state")
async def put_state(request: Request, state: State):
    sid = await get_session(request)
    if not maps:
        raise HTTPException(500, "MONGODB_URI is not configured")
    doc = state.model_dump()
    doc.update({"session": sid, "updated_at": datetime.now(timezone.utc).isoformat()})
    await maps.replace_one({"session": sid}, doc, upsert=True)
    response = JSONResponse({"ok": True})
    if not request.cookies.get("world_map_session"):
        response.set_cookie("world_map_session", sid, max_age=31536000, httponly=True, samesite="lax")
    return response

@app.get("/api/search")
async def search(q: str):
    if not q.strip(): return []
    params = {"q": q, "format": "jsonv2", "limit": 8, "polygon_geojson": 1, "addressdetails": 1, "namedetails": 1}
    headers = {"User-Agent": "WorldAISizeMap/1.0 (contact: admin@example.com)"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers)
    if r.status_code != 200: raise HTTPException(r.status_code, "Nominatim search failed")
    out=[]
    for x in r.json():
        if not x.get("geojson"): continue
        out.append({"osm_id": x.get("osm_id"), "osm_type": x.get("osm_type"), "name": x.get("display_name", "").split(",")[0],
                    "display_name": x.get("display_name"), "lat": float(x["lat"]), "lon": float(x["lon"]),
                    "type": x.get("type"), "category": x.get("category"), "geojson": x["geojson"],
                    "address": x.get("address", {})})
    return out

@app.post("/api/groq-prompt")
async def groq_prompt(payload: dict[str, Any]):
    if not GROQ_API_KEY: raise HTTPException(500, "GROQ_API_KEY is not configured")
    name = payload.get("name", "this place")
    prompt = f"Create one concise English image prompt for a beautiful realistic editorial image representing {name}. No text, no logos, no map labels."
    body={"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":prompt}],"temperature":0.7}
    headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
    async with httpx.AsyncClient(timeout=45) as client:
        r=await client.post("https://api.groq.com/openai/v1/chat/completions",headers=headers,json=body)
    if r.status_code >= 400: raise HTTPException(r.status_code, r.text[:500])
    return {"prompt": r.json()["choices"][0]["message"]["content"].strip()}

@app.post("/api/generate-image")
async def generate_image(payload: ImageRequest):
    if not CF_ACCOUNT_ID or not CF_TOKEN: raise HTTPException(500, "Cloudflare credentials are not configured")
    url=f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"
    headers={"Authorization":f"Bearer {CF_TOKEN}","Content-Type":"application/json"}
    body={"prompt": payload.prompt, "steps": 4}
    async with httpx.AsyncClient(timeout=120) as client:
        r=await client.post(url,headers=headers,json=body)
    if r.status_code >= 400: raise HTTPException(r.status_code, r.text[:1000])
    ctype=r.headers.get("content-type","")
    if "application/json" in ctype:
        data=r.json(); result=data.get("result",data)
        if isinstance(result, dict) and result.get("image"):
            return {"image": "data:image/jpeg;base64," + result["image"]}
        return {"image": None, "raw": data}
    return {"image": "data:image/jpeg;base64," + base64.b64encode(r.content).decode()}

@app.post("/api/ai-label")
async def ai_label(payload: dict[str, Any]):
    if not GROQ_API_KEY: return {"label": payload.get("name", "")}
    name=payload.get("name","")
    body={"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":f"Return only a short label (2-5 words) for {name}."}],"temperature":0.2}
    headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.post("https://api.groq.com/openai/v1/chat/completions",headers=headers,json=body)
    if r.status_code >= 400: return {"label": name}
    return {"label": r.json()["choices"][0]["message"]["content"].strip().strip('"')}
