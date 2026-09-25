"""Media assets and their links to recipe steps and ingredients."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import MediaType, StepImageStatus

if TYPE_CHECKING:
    from app.models.recipe import Ingredient, Recipe, RecipeStep


class MediaAsset(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A stored file. `storage_key` is backend-agnostic; URLs are built at read time."""

    __tablename__ = "media_assets"
    __table_args__ = (Index("ix_media_assets_recipe_id_type", "recipe_id", "type"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    type: Mapped[MediaType] = mapped_column(pg_enum(MediaType, "media_type"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Probe results, image dimensions, alt text etc. ("metadata" is reserved by SQLAlchemy).
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Upload order of cooking photos.
    position: Mapped[int | None] = mapped_column(Integer)

    recipe: Mapped["Recipe"] = relationship(back_populates="media_assets", foreign_keys=[recipe_id])


class StepImage(UUIDPrimaryKeyMixin, Base):
    """Links a cooking photo to a step. `step_id` is null while the photo is unmatched."""

    __tablename__ = "step_images"

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recipe_steps.id", ondelete="SET NULL"), index=True
    )
    # One photo belongs to at most one step.
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), unique=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[StepImageStatus] = mapped_column(
        pg_enum(StepImageStatus, "step_image_status"),
        default=StepImageStatus.UNMATCHED,
        server_default=StepImageStatus.UNMATCHED.value,
    )
    reason: Mapped[str | None] = mapped_column(Text)

    step: Mapped["RecipeStep | None"] = relationship()
    media_asset: Mapped[MediaAsset] = relationship()


class IngredientImage(UUIDPrimaryKeyMixin, Base):
    """A remotely hosted, licensed image for an ingredient (never AI-generated)."""

    __tablename__ = "ingredient_images"

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), unique=True
    )
    image_url: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(200))
    attribution: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    alt_text: Mapped[str | None] = mapped_column(String(300))

    ingredient: Mapped["Ingredient"] = relationship()
