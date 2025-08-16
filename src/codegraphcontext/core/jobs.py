# src/codegraphcontext/core/jobs.py
import uuid
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

class JobStatus(Enum):
    """Job status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class JobInfo:
    """Data class for job information"""
    job_id: str
    status: JobStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    total_files: int = 0
    processed_files: int = 0
    current_file: Optional[str] = None
    estimated_duration: Optional[float] = None
    actual_duration: Optional[float] = None
    errors: List[str] = None
    result: Optional[Dict[str, Any]] = None
    path: Optional[str] = None
    is_dependency: bool = False

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Calculate estimated time remaining"""
        if self.status != JobStatus.RUNNING or self.processed_files == 0:
            return None
        elapsed = (datetime.now() - self.start_time).total_seconds()
        avg_time_per_file = elapsed / self.processed_files
        remaining_files = self.total_files - self.processed_files
        return remaining_files * avg_time_per_file

class JobManager:
    """Manager for background jobs"""
    def __init__(self):
        self.jobs: Dict[str, JobInfo] = {}
        self.lock = threading.Lock()

    def create_job(self, path: str, is_dependency: bool = False) -> str:
        """Create a new job and return job ID"""
        job_id = str(uuid.uuid4())
        with self.lock:
            self.jobs[job_id] = JobInfo(
                job_id=job_id,
                status=JobStatus.PENDING,
                start_time=datetime.now(),
                path=path,
                is_dependency=is_dependency
            )
        return job_id

    def update_job(self, job_id: str, **kwargs):
        """Update job information"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """Get job information"""
        with self.lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> List[JobInfo]:
        """List all jobs"""
        with self.lock:
            return list(self.jobs.values())

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up jobs older than specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        with self.lock:
            jobs_to_remove = [
                job_id for job_id, job in self.jobs.items()
                if job.end_time and job.end_time < cutoff_time
            ]
            for job_id in jobs_to_remove:
                del self.jobs[job_id]