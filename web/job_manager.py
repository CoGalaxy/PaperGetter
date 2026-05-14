"""任务管理器 — 内存队列 + 后台线程执行."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from paper_get_agent.models.paper import AnalysisReport
from paper_get_agent.orchestrator import PaperAgent, report_to_markdown


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class AnalysisJob:
    id: str
    filename: str
    file_path: str
    skip_validation: bool = True
    status: JobStatus = JobStatus.QUEUED
    created_at: str = ""
    progress_events: list[dict] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    result: AnalysisReport | None = None
    error: str | None = None
    thread: threading.Thread | None = None
    overall_summary: str = ""

    @property
    def result_json(self) -> dict | None:
        if self.result is None:
            return None
        return self.result.model_dump()

    @property
    def result_markdown(self) -> str:
        if self.result is None:
            return ""
        return report_to_markdown(self.result)


class JobManager:
    """内存中的任务管理器."""

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._streams: dict[str, asyncio.Queue] = {}

    def create_job(self, filename: str, file_path: str, skip_validation: bool = True) -> AnalysisJob:
        import datetime
        job = AnalysisJob(
            skip_validation=skip_validation,
            id=uuid.uuid4().hex[:12],
            filename=filename,
            file_path=file_path,
            created_at=datetime.datetime.now().isoformat(),
        )
        self._jobs[job.id] = job
        self._streams[job.id] = asyncio.Queue()
        return job

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [
            {
                "id": j.id,
                "filename": j.filename,
                "status": j.status.value,
                "created_at": j.created_at,
            }
            for j in reversed(list(self._jobs.values()))
        ]

    def delete_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            if job.status == JobStatus.RUNNING:
                job.cancel_event.set()
                if job.thread:
                    job.thread.join(timeout=5)
            del self._jobs[job_id]
            self._streams.pop(job_id, None)
            return True
        return False

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.RUNNING:
            job.cancel_event.set()
            return True
        return False

    async def run_job(self, job: AnalysisJob) -> AnalysisReport:
        """在后台线程中执行分析，通过 asyncio.Queue 推进度事件."""
        queue = self._streams.get(job.id)
        if queue is None:
            raise ValueError(f"Job {job.id} not found")

        job.status = JobStatus.RUNNING
        loop = asyncio.get_running_loop()

        progress_buf: list[str] = []
        last_flush = [0.0]

        def on_progress(phase: str, step: str, detail: str, elapsed: float) -> None:
            if job.cancel_event.is_set():
                raise InterruptedError("Job cancelled")
            evt = {"phase": phase, "step": step, "detail": detail, "elapsed": elapsed}
            job.progress_events.append(evt)
            loop.call_soon_threadsafe(queue.put_nowait, evt)

            # 累积 LLM 流式输出
            if step == "llm_chunk":
                progress_buf.append(detail)
                now = elapsed
                if now - last_flush[0] > 0.2 or len(progress_buf) > 20:
                    last_flush[0] = now
                    chunk_text = "".join(progress_buf)
                    progress_buf.clear()
                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "phase": phase,
                        "step": "llm_flush",
                        "detail": chunk_text,
                        "elapsed": elapsed,
                    })

        def run_in_thread() -> None:
            try:
                agent = PaperAgent(skip_validation=job.skip_validation)
                result = agent.analyze(
                    job.file_path,
                    on_progress=on_progress,
                )
                job.result = result
                job.status = JobStatus.DONE
                loop.call_soon_threadsafe(queue.put_nowait, {"phase": "", "step": "job_done", "detail": job.id, "elapsed": 0})
            except InterruptedError:
                job.status = JobStatus.CANCELLED
                loop.call_soon_threadsafe(queue.put_nowait, {"phase": "", "step": "job_error", "detail": "任务已取消", "elapsed": 0})
            except Exception as e:
                job.status = JobStatus.ERROR
                job.error = str(e)
                loop.call_soon_threadsafe(queue.put_nowait, {"phase": "", "step": "job_error", "detail": str(e), "elapsed": 0})

        job.thread = threading.Thread(target=run_in_thread, daemon=True)
        job.thread.start()
        return job.result  # Will be None until completion; caller uses stream

    def get_stream_queue(self, job_id: str) -> asyncio.Queue | None:
        return self._streams.get(job_id)


# 全局单例
manager = JobManager()
