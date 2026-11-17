import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.config import BASE_DIR, CLIPS_DIR, config
from app.stream_ingest import stream_ingest
from app.clipper import clip_manager
from app.hotkey_listener import hotkey_manager
from app.transcriber import transcriber
from app.url_clipper import url_clipper

app = FastAPI(title="OpenShort LiveClipper", version="1.0.0")

# Mount static and clips folders
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/clips_media", StaticFiles(directory=str(CLIPS_DIR)), name="clips_media")

# Active WebSocket clients
connected_clients: Set[WebSocket] = set()

# Main thread event loop reference for thread-safe websocket broadcasts
main_loop: asyncio.AbstractEventLoop = None

class StartRequest(BaseModel):
    source_type: str # 'url', 'desktop', 'file', 'simulator'
    source_target: str = ""

class ConfigUpdateRequest(BaseModel):
    pre_roll: int
    post_roll: int
    excitement_threshold: int
    audio_sensitivity: float
    motion_sensitivity: float
    audio_weight: float
    motion_weight: float
    chat_weight: float
    auto_generate_shorts: bool
    shorts_style: str

class TrimRequest(BaseModel):
    start_time: float
    end_time: float

class LinkClipRequest(BaseModel):
    url: str
    start_time: float | None = None
    duration: float | None = 20.0
    mode: str = "auto" # 'auto' or 'manual_range'
    auto_short: bool = True

class EnhanceRequest(BaseModel):
    color_pop: bool = True
    audio_loudnorm: bool = True
    burn_captions: bool = False

class ShortRequest(BaseModel):
    style: str = "studio_glow" # 'studio_glow', 'stacked_split', 'action_zoom'
    burn_captions: bool = False
    color_pop: bool = True
    audio_enhance: bool = True

def broadcast_ws_message(msg_type: str, data: dict):
    """Safely broadcasts a message to all connected WebSocket UI clients."""
    global main_loop
    if not connected_clients:
        return

    payload = json.dumps({"type": msg_type, "data": data})
    if main_loop and main_loop.is_running():
        for ws in list(connected_clients):
            asyncio.run_coroutine_threadsafe(ws.send_text(payload), main_loop)

# Register callbacks with stream ingest
def on_telemetry(data: dict):
    broadcast_ws_message("telemetry", data)

def on_new_clip(clip_data: dict):
    broadcast_ws_message("new_clip", clip_data)

stream_ingest.set_callbacks(on_telemetry, on_new_clip)

# Start global hotkey listener
hotkey_manager.start(on_trigger=lambda reason: stream_ingest.trigger_manual_clip(reason))

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    print("[Server] OpenShort LiveClipper Server started on http://localhost:8000")

@app.on_event("shutdown")
async def shutdown_event():
    stream_ingest.stop_ingestion()
    hotkey_manager.stop()

@app.get("/")
async def get_index():
    index_file = STATIC_DIR / "index.html"
    return FileResponse(index_file)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        # Send initial state
        initial_state = {
            "is_active": stream_ingest.is_active,
            "source_type": stream_ingest.source_type,
            "source_target": stream_ingest.source_target,
            "config": config.__dict__,
            "clips": clip_manager.get_all_clips()
        }
        await websocket.send_text(json.dumps({"type": "init", "data": initial_state}))

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "clip_now":
                clip = stream_ingest.trigger_manual_clip("Dashboard Instant Clip")
                if clip:
                    await websocket.send_text(json.dumps({"type": "new_clip", "data": clip}))
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception as e:
        connected_clients.discard(websocket)

@app.get("/api/status")
async def get_status():
    return {
        "is_active": stream_ingest.is_active,
        "source_type": stream_ingest.source_type,
        "source_target": stream_ingest.source_target
    }

@app.post("/api/start")
async def start_stream(req: StartRequest):
    success = stream_ingest.start_ingestion(req.source_type, req.source_target)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start stream ingestion.")
    broadcast_ws_message("status_change", {"is_active": True, "source_type": req.source_type})
    return {"status": "started", "source_type": req.source_type}

@app.post("/api/stop")
async def stop_stream():
    stream_ingest.stop_ingestion()
    broadcast_ws_message("status_change", {"is_active": False})
    return {"status": "stopped"}

@app.post("/api/clip_now")
async def clip_now():
    clip = stream_ingest.trigger_manual_clip("API Instant Clip")
    if not clip:
        raise HTTPException(status_code=400, detail="Unable to extract clip. Buffer may be empty.")
    return clip

@app.post("/api/clip_from_link")
async def clip_from_link_endpoint(req: LinkClipRequest):
    # Run link extraction in thread pool to avoid blocking async loop
    clip = await asyncio.to_thread(
        url_clipper.clip_link,
        url=req.url,
        start_time=req.start_time,
        duration=req.duration,
        mode=req.mode,
        auto_short=req.auto_short
    )
    if not clip:
        raise HTTPException(status_code=400, detail="Failed to extract clip from link. Verify the URL is public and valid.")
    broadcast_ws_message("new_clip", clip)
    return clip

@app.get("/api/clips")
async def get_clips():
    return clip_manager.get_all_clips()

@app.post("/api/clips/{clip_id}/short")
async def create_short(clip_id: str, req: ShortRequest = None):
    style = req.style if req else "studio_glow"
    burn_captions = req.burn_captions if req else False
    color_pop = req.color_pop if req else True
    audio_enhance = req.audio_enhance if req else True
    short_fn = await asyncio.to_thread(
        clip_manager.convert_to_short,
        clip_id=clip_id,
        style=style,
        burn_captions=burn_captions,
        color_pop=color_pop,
        audio_enhance=audio_enhance
    )
    if not short_fn:
        raise HTTPException(status_code=500, detail="Failed to convert clip to 9:16 short.")
    return {"status": "success", "short_filename": short_fn}

@app.post("/api/clips/{clip_id}/enhance")
async def enhance_clip_endpoint(clip_id: str, req: EnhanceRequest):
    enhanced = await asyncio.to_thread(
        clip_manager.enhance_clip,
        clip_id=clip_id,
        color_pop=req.color_pop,
        audio_loudnorm=req.audio_loudnorm,
        burn_captions=req.burn_captions
    )
    if not enhanced:
        raise HTTPException(status_code=500, detail="Failed to enhance clip.")
    broadcast_ws_message("new_clip", enhanced)
    return enhanced

@app.post("/api/clips/{clip_id}/trim")
async def trim_clip_endpoint(clip_id: str, req: TrimRequest):
    trimmed = clip_manager.trim_clip(clip_id, req.start_time, req.end_time)
    if not trimmed:
        raise HTTPException(status_code=500, detail="Failed to trim clip.")
    broadcast_ws_message("new_clip", trimmed)
    return trimmed

@app.post("/api/clips/{clip_id}/transcribe")
async def transcribe_endpoint(clip_id: str):
    clip = next((c for c in clip_manager.metadata if c["id"] == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found.")
    srt_file = transcriber.transcribe_clip(clip["filename"])
    if not srt_file:
        raise HTTPException(status_code=500, detail="Failed to transcribe clip.")
    clip["srt_file"] = srt_file
    clip_manager._save_metadata()
    return {"status": "success", "srt_file": srt_file}

@app.post("/api/clips/{clip_id}/open")
async def open_explorer_endpoint(clip_id: str):
    success = clip_manager.open_in_explorer(clip_id)
    return {"status": "success" if success else "failed"}

@app.delete("/api/clips/{clip_id}")
async def delete_clip_endpoint(clip_id: str):
    success = clip_manager.delete_clip(clip_id)
    if not success:
        raise HTTPException(status_code=404, detail="Clip not found.")
    broadcast_ws_message("delete_clip", {"id": clip_id})
    return {"status": "deleted", "id": clip_id}

@app.get("/api/config")
async def get_config():
    return config.__dict__

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    config.pre_roll = req.pre_roll
    config.post_roll = req.post_roll
    config.excitement_threshold = req.excitement_threshold
    config.audio_sensitivity = req.audio_sensitivity
    config.motion_sensitivity = req.motion_sensitivity
    config.audio_weight = req.audio_weight
    config.motion_weight = req.motion_weight
    config.chat_weight = req.chat_weight
    config.auto_generate_shorts = req.auto_generate_shorts
    config.shorts_style = req.shorts_style
    config.save()
    broadcast_ws_message("config_updated", config.__dict__)
    return {"status": "updated", "config": config.__dict__}
