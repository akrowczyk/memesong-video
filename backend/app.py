from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.aligner import align_lyrics, get_audio_duration
from backend.renderer import THEMES, render_karaoke_video

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
PROJECTS_DIR = ROOT_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MemeSong Lyric Video Studio")


@app.middleware("http")
async def no_cache_frontend(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# In-memory background job registry
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _create_job(kind: str, project_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "kind": kind,
            "project_id": project_id,
            "status": "running",
            "message": "Starting...",
            "progress": 0.0,
            "error": None,
            "result": None,
        }
    return job_id


def _update_job(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def _safe_project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{3,64}", project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return pdir


def _load_project_state(project_id: str) -> dict[str, Any]:
    pdir = _safe_project_dir(project_id)
    meta_path = pdir / "project.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Project metadata missing")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    timings_path = pdir / "timings.json"
    timings = json.loads(timings_path.read_text(encoding="utf-8")) if timings_path.exists() else None
    cover_file = _find_cover_file(pdir)
    video_file = pdir / "output.mp4"

    return {
        **meta,
        "has_timings": timings is not None,
        "timings": timings,
        "has_cover": cover_file is not None,
        "has_video": video_file.exists(),
        "audio_url": f"/api/projects/{project_id}/audio",
        "cover_url": f"/api/projects/{project_id}/cover?v={int(cover_file.stat().st_mtime)}" if cover_file else None,
        "video_url": f"/api/projects/{project_id}/video.mp4?v={int(video_file.stat().st_mtime)}" if video_file.exists() else None,
    }


def _find_audio_file(pdir: Path) -> Path:
    for ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        candidate = pdir / f"audio{ext}"
        if candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail="Audio file not found")


def _find_cover_file(pdir: Path) -> Path | None:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = pdir / f"cover{ext}"
        if candidate.exists():
            return candidate
    return None


class AlignRequest(BaseModel):
    lyrics: str | None = None
    isolate_vocals: bool = True
    model_name: str = "base"
    language: str = "en"


class SaveProjectRequest(BaseModel):
    timings: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    lyrics: str | None = None


class RenderRequest(BaseModel):
    settings: dict[str, Any] | None = None


@app.get("/")
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse({"message": "Frontend not built yet."})
    return FileResponse(index_path)


@app.get("/api/themes")
def list_themes():
    return {
        name: {
            "bg1": f"rgb{cfg['bg1']}",
            "bg2": f"rgb{cfg['bg2']}",
            "orb1": f"rgb{cfg['orb1']}",
            "orb2": f"rgb{cfg['orb2']}",
            "accent": cfg["accent"],
        }
        for name, cfg in THEMES.items()
    }


@app.get("/api/projects")
def list_projects():
    items = []
    for pdir in PROJECTS_DIR.iterdir():
        meta_path = pdir / "project.json"
        if pdir.is_dir() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "id": meta["id"],
                        "title": meta.get("settings", {}).get("title") or meta.get("audio_filename", "Untitled"),
                        "artist": meta.get("settings", {}).get("artist", ""),
                        "duration": meta.get("duration", 0),
                        "created_at": meta.get("created_at", 0),
                        "has_timings": (pdir / "timings.json").exists(),
                        "has_video": (pdir / "output.mp4").exists(),
                    }
                )
            except Exception:
                continue
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"projects": items}


@app.post("/api/projects")
async def create_project(
    audio: UploadFile = File(...),
    lyrics: str = Form(""),
    title: str = Form(""),
    artist: str = Form(""),
    cover: UploadFile | None = File(None),
):
    ext = Path(audio.filename or "song.mp3").suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        ext = ".mp3"

    slug = re.sub(r"[^a-z0-9]+", "-", Path(audio.filename or "song").stem.lower()).strip("-")[:24] or "song"
    project_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    pdir = PROJECTS_DIR / project_id
    pdir.mkdir(parents=True, exist_ok=True)

    audio_path = pdir / f"audio{ext}"
    audio_bytes = await audio.read()
    audio_path.write_bytes(audio_bytes)

    try:
        duration = get_audio_duration(audio_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read audio file with ffprobe: {exc}")

    has_cover = False
    if cover is not None and cover.filename:
        c_ext = Path(cover.filename).suffix.lower()
        if c_ext not in (".png", ".jpg", ".jpeg", ".webp"):
            c_ext = ".png"
        (pdir / f"cover{c_ext}").write_bytes(await cover.read())
        has_cover = True

    default_title = title.strip() or Path(audio.filename or "Untitled").stem
    meta = {
        "id": project_id,
        "audio_filename": audio.filename or f"audio{ext}",
        "duration": round(duration, 3),
        "lyrics": lyrics,
        "created_at": time.time(),
        "settings": {
            "title": default_title,
            "artist": artist.strip(),
            "theme_name": "midnight",
            "accent_color": str(THEMES["midnight"]["accent"]),
            "use_cover_image": has_cover,
            "time_offset": 0.0,
            "lyric_position": "bottom" if has_cover else "center",
            "bg_dim": 0.15,
            "text_outline": "dark",
            "show_neighbor_lines": False,
        },
    }
    (pdir / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return _load_project_state(project_id)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return _load_project_state(project_id)


@app.post("/api/projects/{project_id}/cover")
async def upload_cover(project_id: str, cover: UploadFile = File(...)):
    pdir = _safe_project_dir(project_id)
    for old in pdir.glob("cover.*"):
        old.unlink(missing_ok=True)
    c_ext = Path(cover.filename or "cover.png").suffix.lower()
    if c_ext not in (".png", ".jpg", ".jpeg", ".webp"):
        c_ext = ".png"
    (pdir / f"cover{c_ext}").write_bytes(await cover.read())

    meta_path = pdir / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("settings", {})["use_cover_image"] = True
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return _load_project_state(project_id)


@app.delete("/api/projects/{project_id}/cover")
def delete_cover(project_id: str):
    pdir = _safe_project_dir(project_id)
    for old in pdir.glob("cover.*"):
        old.unlink(missing_ok=True)
    meta_path = pdir / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("settings", {})["use_cover_image"] = False
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return _load_project_state(project_id)


@app.put("/api/projects/{project_id}/timings")
def save_project(project_id: str, payload: SaveProjectRequest):
    pdir = _safe_project_dir(project_id)
    meta_path = pdir / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if payload.lyrics is not None:
        meta["lyrics"] = payload.lyrics
    if payload.settings is not None:
        meta.setdefault("settings", {}).update(payload.settings)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if payload.timings is not None:
        (pdir / "timings.json").write_text(json.dumps(payload.timings, indent=2), encoding="utf-8")

    return _load_project_state(project_id)


@app.post("/api/projects/{project_id}/align")
def start_alignment(project_id: str, req: AlignRequest):
    pdir = _safe_project_dir(project_id)
    audio_path = _find_audio_file(pdir)
    meta_path = pdir / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    lyrics_text = req.lyrics if req.lyrics is not None else meta.get("lyrics", "")
    if not lyrics_text.strip():
        raise HTTPException(status_code=400, detail="Please enter lyrics before aligning.")

    if req.lyrics is not None:
        meta["lyrics"] = req.lyrics
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    job_id = _create_job("align", project_id)

    def _worker():
        try:
            timings = align_lyrics(
                audio_path,
                lyrics_text,
                pdir,
                isolate_vocals=req.isolate_vocals,
                model_name=req.model_name,
                language=req.language,
                on_progress=lambda msg, pct: _update_job(job_id, message=msg, progress=round(pct, 3)),
            )
            _update_job(job_id, status="done", progress=1.0, message="Alignment complete!", result=timings)
        except Exception as exc:
            _update_job(job_id, status="error", error=str(exc), message=f"Alignment failed: {exc}")

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/projects/{project_id}/render")
def start_render(project_id: str, req: RenderRequest):
    pdir = _safe_project_dir(project_id)
    audio_path = _find_audio_file(pdir)
    timings_path = pdir / "timings.json"
    if not timings_path.exists():
        raise HTTPException(status_code=400, detail="Align lyrics first before rendering.")

    meta_path = pdir / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if req.settings:
        meta.setdefault("settings", {}).update(req.settings)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    settings = meta.get("settings", {})
    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    cover_file = _find_cover_file(pdir)
    output_path = pdir / "output.mp4"

    job_id = _create_job("render", project_id)

    def _worker():
        try:
            render_karaoke_video(
                audio_path,
                timings,
                output_path,
                theme_name=settings.get("theme_name", "midnight"),
                accent_color=settings.get("accent_color"),
                title=settings.get("title", ""),
                artist=settings.get("artist", ""),
                cover_image_path=cover_file,
                use_cover_image=bool(settings.get("use_cover_image", False)),
                time_offset=float(settings.get("time_offset", 0.0)),
                lyric_position=str(settings.get("lyric_position", "center")),
                bg_dim=float(settings.get("bg_dim", 0.15)),
                text_outline=settings.get("text_outline", "dark"),
                show_neighbor_lines=bool(settings.get("show_neighbor_lines", False)),
                on_progress=lambda msg, pct: _update_job(job_id, message=msg, progress=round(pct, 3)),
            )
            _update_job(
                job_id,
                status="done",
                progress=1.0,
                message="Video exported!",
                result={"video_url": f"/api/projects/{project_id}/video.mp4?v={int(time.time())}"},
            )
        except Exception as exc:
            _update_job(job_id, status="error", error=str(exc), message=f"Render failed: {exc}")

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(job)


@app.get("/api/projects/{project_id}/audio")
def serve_audio(project_id: str):
    pdir = _safe_project_dir(project_id)
    audio_path = _find_audio_file(pdir)
    return FileResponse(audio_path)


@app.get("/api/projects/{project_id}/cover")
def serve_cover(project_id: str):
    pdir = _safe_project_dir(project_id)
    cover_path = _find_cover_file(pdir)
    if not cover_path:
        raise HTTPException(status_code=404, detail="Cover image not found")
    return FileResponse(cover_path)


@app.get("/api/projects/{project_id}/video.mp4")
def serve_video(project_id: str):
    pdir = _safe_project_dir(project_id)
    video_path = pdir / "output.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Rendered video not found")
    meta = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", meta.get("settings", {}).get("title") or project_id).strip("_") or "lyric_video"
    return FileResponse(video_path, media_type="video/mp4", filename=f"{slug}_x.mp4")
