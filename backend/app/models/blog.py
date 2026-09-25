"""Generated blog article for a recipe."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import BlogStatus

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class Blog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "blogs"

    # One blog per recipe.
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[BlogStatus] = mapped_column(
        pg_enum(BlogStatus, "blog_status"),
        default=BlogStatus.DRAFT,
        server_default=BlogStatus.DRAFT.value,
    )
    title: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    meta_title: Mapped[str | None] = mapped_column(String(300))
    meta_description: Mapped[str | None] = mapped_column(String(500))
    content_html: Mapped[str | None] = mapped_column(Text)
    content_markdown: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    primary_keyword: Mapped[str | None] = mapped_column(String(200))
    secondary_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), default=list, server_default=text("'{}'")
    )
    og_title: Mapped[str | None] = mapped_column(String(300))
    og_description: Mapped[str | None] = mapped_column(String(500))
    hero_alt_text: Mapped[str | None] = mapped_column(String(300))
    json_ld: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    faq: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipe: Mapped["Recipe"] = relationship(back_populates="blog")
