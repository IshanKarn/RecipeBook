"""Background processing job for a recipe."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import JobStatus, JobStep

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
        index=True,
    )
    current_step: Mapped[JobStep] = mapped_column(
        pg_enum(JobStep, "job_step"),
        default=JobStep.UPLOADED,
        server_default=JobStep.UPLOADED.value,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Safe, user-facing message and code; full details live in the server logs.
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    celery_task_id: Mapped[str | None] = mapped_column(String(255))

    recipe: Mapped["Recipe"] = relationship(back_populates="jobs")
