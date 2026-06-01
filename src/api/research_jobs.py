"""In-memory background job registry for long-running local research workflows."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Callable


ResearchCallable = Callable[[], dict[str, Any]]
WorkflowCallable = Callable[[str], dict[str, Any] | None]


class ResearchJobRegistry:
    """Run slow multi-agent workflows without blocking the web request thread."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research-job")
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(
        self,
        *,
        symbol: str,
        execute: ResearchCallable,
        workflow: WorkflowCallable,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        job = {
            "job_id": job_id,
            "symbol": symbol,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "workflow": None,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run, job_id, symbol, execute, workflow)
        return self.get(job_id, workflow=workflow) or deepcopy(job)

    def get(
        self,
        job_id: str,
        *,
        workflow: WorkflowCallable | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            job = deepcopy(self._jobs.get(job_id))
        if not job:
            return None
        if workflow and job["status"] in {"queued", "running"}:
            job["workflow"] = workflow(str(job["symbol"]))
        return job

    def _run(
        self,
        job_id: str,
        symbol: str,
        execute: ResearchCallable,
        workflow: WorkflowCallable,
    ) -> None:
        self._update(job_id, status="running")
        try:
            result = execute()
            self._update(job_id, status="completed", result=result, workflow=workflow(symbol))
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc), workflow=workflow(symbol))

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = datetime.now().isoformat()
