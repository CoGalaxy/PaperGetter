"""FastAPI 服务器 — Web 入口."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config_api import get_config, update_config
from .job_manager import JobStatus, manager

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
PAPERS_DIR = Path(__file__).parent.parent / "papers"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

PAPERS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Paper Get Agent", version="0.2.0")


# ── 静态文件 ──────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/favicon.ico")
async def favicon() -> Response:
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return Response(status_code=204)


# ── 健康检查 ──────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


# ── 文件上传 ──────────────────────────────

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "只支持 PDF 文件")

    ts = int(time.time())
    safe_name = file.filename.replace(" ", "_").replace("/", "_")
    dest = PAPERS_DIR / f"{ts}_{safe_name}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "path": str(dest),
        "filename": file.filename,
        "size": dest.stat().st_size,
    }


# ── 任务管理 ──────────────────────────────

@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), validate: str = "false") -> dict:
    """上传 PDF 并创建分析任务. validate=true 启用代码验证."""
    skip_validation = validate.lower() != "true"

    ts = int(time.time())
    safe_name = (file.filename or "paper.pdf").replace(" ", "_").replace("/", "_")
    dest = PAPERS_DIR / f"{ts}_{safe_name}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = manager.create_job(
        filename=file.filename or "paper.pdf",
        file_path=str(dest),
        skip_validation=skip_validation,
    )
    # 启动分析（异步不阻塞）
    asyncio.create_task(manager.run_job(job))

    return {"job_id": job.id, "filename": job.filename, "status": job.status.value, "validation_enabled": not skip_validation}


@app.get("/api/jobs")
async def list_jobs() -> list[dict]:
    return manager.list_jobs()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status.value,
        "created_at": job.created_at,
        "error": job.error,
        "event_count": len(job.progress_events),
    }


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    ok = manager.delete_job(job_id)
    if not ok:
        raise HTTPException(404, "任务不存在")
    return {"deleted": True}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    ok = manager.cancel_job(job_id)
    if not ok:
        raise HTTPException(404, "任务不存在或未在运行")
    return {"cancelled": True}


# ── SSE 进度流 ────────────────────────────

@app.get("/api/jobs/{job_id}/stream")
async def stream_progress(job_id: str, request: Request) -> StreamingResponse:
    queue = manager.get_stream_queue(job_id)
    if queue is None:
        raise HTTPException(404, "任务不存在")

    async def generate():
        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30)
                step = evt.get("step", "")
                if step == "job_done":
                    yield f"event: job_done\ndata: {json.dumps({'job_id': job_id}, ensure_ascii=False)}\n\n"
                    break
                elif step == "job_error":
                    yield f"event: job_error\ndata: {json.dumps({'job_id': job_id, 'error': evt.get('detail', '')}, ensure_ascii=False)}\n\n"
                    break
                elif step == "llm_flush":
                    chunk_data = json.dumps({"text": evt.get("detail", ""), "phase": evt.get("phase", "")}, ensure_ascii=False)
                    yield f"event: llm_chunk\ndata: {chunk_data}\n\n"
                else:
                    pct = _estimate_pct(evt)
                    evt["pct"] = pct
                    yield f"event: progress\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield f"event: ping\ndata: {json.dumps({})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _estimate_pct(evt: dict) -> int:
    """根据 phase + step 估算整体进度 0-100."""
    phase = evt.get("phase", "")
    step = evt.get("step", "")
    weights = {"parse": 10, "extract": 30, "validate": 30, "analyze": 15, "summarize": 10, "report": 5}
    base = {"parse": 0, "extract": 10, "validate": 40, "analyze": 70, "summarize": 85, "report": 95}
    pct = base.get(phase, 0)
    if step == "done":
        pct += weights.get(phase, 0)
    elif step not in ("start", "skip"):
        pct += weights.get(phase, 0) // 2
    return min(100, pct)


# ── 报告获取 ──────────────────────────────

@app.get("/api/reports/{job_id}/json")
async def get_report_json(job_id: str) -> dict:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if job.status != JobStatus.DONE:
        raise HTTPException(400, "任务尚未完成")
    return job.result_json or {}


@app.get("/api/reports/{job_id}/markdown")
async def get_report_markdown(job_id: str) -> Response:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if job.status != JobStatus.DONE:
        raise HTTPException(400, "任务尚未完成")
    md = job.result_markdown
    safe_name = job.filename.rsplit(".", 1)[0].replace(" ", "_")
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_analysis.md"},
    )


# ── 配置 ──────────────────────────────────

@app.get("/api/config")
async def config_get() -> dict:
    return get_config()


@app.put("/api/config")
async def config_update(data: dict) -> dict:
    try:
        return update_config(data)
    except Exception as e:
        raise HTTPException(422, f"配置校验失败: {e}")


@app.get("/api/models")
async def model_list() -> dict:
    """返回当前配置中的模型名列表（供前端下拉框用）."""
    cfg = get_config()
    models = cfg.get("llm", {}).get("models", {})
    names = sorted(set(models.values()))
    return {"models": names, "assignments": models}


# ── 启动 ──────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=True)
