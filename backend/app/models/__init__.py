"""Importing this package registers every model on `Base.metadata` (used by Alembic)."""

from app.models.blog import Blog
from app.models.enums import (
    BlogStatus,
    JobStatus,
    JobStep,
    Language,
    MediaType,
    RecipeStatus,
    StepImageStatus,
)
from app.models.job import Job
from app.models.media import IngredientImage, MediaAsset, StepImage
from app.models.recipe import CookingSuggestion, Ingredient, Recipe, RecipeStep

__all__ = [
    "Blog",
    "BlogStatus",
    "CookingSuggestion",
    "Ingredient",
    "IngredientImage",
    "Job",
    "JobStatus",
    "JobStep",
    "Language",
    "MediaAsset",
    "MediaType",
    "Recipe",
    "RecipeStatus",
    "RecipeStep",
    "StepImage",
    "StepImageStatus",
]
