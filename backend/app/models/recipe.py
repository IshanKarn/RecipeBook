"""Recipe aggregate: recipe, ingredients, steps and cooking suggestions."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.models.enums import Language, RecipeStatus

if TYPE_CHECKING:
    from app.models.blog import Blog
    from app.models.job import Job
    from app.models.media import IngredientImage, MediaAsset, StepImage


class Recipe(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recipes"

    title: Mapped[str | None] = mapped_column(String(300))
    # Null until a blog is generated; unique once set.
    slug: Mapped[str | None] = mapped_column(String(200), unique=True)
    # `language` is what the user asked for; `detected_language` is what the AI found.
    language: Mapped[Language] = mapped_column(
        pg_enum(Language, "language"), default=Language.AUTO, server_default=Language.AUTO.value
    )
    detected_language: Mapped[Language | None] = mapped_column(pg_enum(Language, "language"))
    status: Mapped[RecipeStatus] = mapped_column(
        pg_enum(RecipeStatus, "recipe_status"),
        default=RecipeStatus.UPLOADED,
        server_default=RecipeStatus.UPLOADED.value,
        index=True,
    )
    transcript: Mapped[str | None] = mapped_column(Text)
    dish_name: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    cuisine: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, server_default=text("'{}'")
    )
    hero_media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL", use_alter=True)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[str | None] = mapped_column(String(255), index=True)

    ingredients: Mapped[list["Ingredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Ingredient.position",
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RecipeStep.step_number",
    )
    suggestions: Mapped[list["CookingSuggestion"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CookingSuggestion.position",
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="recipe",
        foreign_keys="MediaAsset.recipe_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    hero_media: Mapped["MediaAsset | None"] = relationship(
        foreign_keys=[hero_media_id], post_update=True
    )
    step_images: Mapped[list["StepImage"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    ingredient_images: Mapped[list["IngredientImage"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    blog: Mapped["Blog | None"] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", passive_deletes=True
    )


def _default_normalized_name(context: DefaultExecutionContext) -> str:
    params = context.get_current_parameters()  # type: ignore[no-untyped-call]
    return str(params["name"]).strip().lower()


class Ingredient(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "position"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    # Lower-cased name used for similarity and image lookups; defaults from `name`.
    normalized_name: Mapped[str] = mapped_column(String(200), default=_default_normalized_name)
    quantity: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class RecipeStep(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recipe_steps"
    __table_args__ = (UniqueConstraint("recipe_id", "step_number"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    step_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    instruction: Mapped[str] = mapped_column(Text)
    duration: Mapped[str | None] = mapped_column(String(100))
    temperature: Mapped[str | None] = mapped_column(String(100))

    recipe: Mapped[Recipe] = relationship(back_populates="steps")


class CookingSuggestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cooking_suggestions"
    __table_args__ = (UniqueConstraint("recipe_id", "position"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    suggestion: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)

    recipe: Mapped[Recipe] = relationship(back_populates="suggestions")
