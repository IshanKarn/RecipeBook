"""Model behaviour against real PostgreSQL: defaults, cascades, uniqueness constraints."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Blog,
    BlogStatus,
    CookingSuggestion,
    Ingredient,
    IngredientImage,
    Job,
    JobStatus,
    JobStep,
    Language,
    MediaAsset,
    MediaType,
    Recipe,
    RecipeStatus,
    RecipeStep,
    StepImage,
    StepImageStatus,
)

pytestmark = pytest.mark.integration


def build_recipe() -> Recipe:
    recipe = Recipe(language=Language.BN, dish_name="Aloo Posto", keywords=["bengali"])
    recipe.ingredients = [
        Ingredient(name="  Potato ", quantity="3", unit="pcs", position=0),
        Ingredient(name="Poppy seeds", quantity=None, notes="Not stated.", position=1),
    ]
    recipe.steps = [
        RecipeStep(step_number=1, title="Cut", instruction="Cut the potatoes."),
        RecipeStep(step_number=2, title="Fry", instruction="Fry until golden."),
    ]
    recipe.suggestions = [CookingSuggestion(suggestion="Use mustard oil.", position=0)]
    return recipe


async def add_media(
    session: AsyncSession, recipe: Recipe, media_type: MediaType = MediaType.COOKING_IMAGE
) -> MediaAsset:
    asset = MediaAsset(
        recipe_id=recipe.id,
        type=media_type,
        storage_key=f"recipes/{recipe.id}/{media_type.value}/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        size_bytes=1234,
        meta={"width": 640},
    )
    session.add(asset)
    await session.flush()
    return asset


async def count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_defaults_are_applied(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()
    await db_session.refresh(recipe, attribute_names=["status", "created_at", "updated_at"])

    assert recipe.status is RecipeStatus.UPLOADED
    assert recipe.created_at is not None and recipe.updated_at is not None
    potato = await db_session.scalar(
        select(Ingredient).where(Ingredient.recipe_id == recipe.id, Ingredient.position == 0)
    )
    assert potato is not None and potato.normalized_name == "potato"

    job = Job(recipe_id=recipe.id)
    db_session.add(job)
    await db_session.flush()
    await db_session.refresh(job)
    assert job.status is JobStatus.QUEUED
    assert job.current_step is JobStep.UPLOADED
    assert job.progress == 0 and job.attempts == 0


async def test_full_graph_insert_and_cascade_delete(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()

    hero = await add_media(db_session, recipe, MediaType.HERO_IMAGE)
    photo = await add_media(db_session, recipe)
    recipe.hero_media_id = hero.id
    db_session.add_all(
        [
            StepImage(
                recipe_id=recipe.id,
                step_id=recipe.steps[0].id,
                media_asset_id=photo.id,
                confidence=0.9,
                status=StepImageStatus.MATCHED,
            ),
            IngredientImage(
                recipe_id=recipe.id,
                ingredient_id=recipe.ingredients[0].id,
                image_url="https://upload.wikimedia.org/potato.jpg",
                provider="wikimedia",
                license="CC BY-SA 4.0",
            ),
            Blog(recipe_id=recipe.id, title="Aloo Posto", slug=f"aloo-posto-{uuid.uuid4().hex}"),
            Job(recipe_id=recipe.id),
        ]
    )
    await db_session.flush()

    for model in (
        Ingredient,
        RecipeStep,
        CookingSuggestion,
        MediaAsset,
        StepImage,
        IngredientImage,
        Blog,
        Job,
    ):
        assert await count(db_session, model) >= 1, model.__name__

    await db_session.delete(recipe)
    await db_session.flush()

    for model in (
        Recipe,
        Ingredient,
        RecipeStep,
        CookingSuggestion,
        MediaAsset,
        StepImage,
        IngredientImage,
        Blog,
        Job,
    ):
        assert await count(db_session, model) == 0, f"{model.__name__} was not cascaded"


async def test_blog_defaults_to_draft(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()
    blog = Blog(recipe_id=recipe.id, title="T", slug=f"t-{uuid.uuid4().hex}")
    db_session.add(blog)
    await db_session.flush()
    await db_session.refresh(blog)
    assert blog.status is BlogStatus.DRAFT
    assert blog.secondary_keywords == []


async def test_duplicate_ingredient_position_is_rejected(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_ingredients_recipe_id_position"):
        async with db_session.begin_nested():
            db_session.add(Ingredient(recipe_id=recipe.id, name="Salt", position=0))
            await db_session.flush()


async def test_duplicate_step_number_is_rejected(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_recipe_steps_recipe_id_step_number"):
        async with db_session.begin_nested():
            db_session.add(
                RecipeStep(recipe_id=recipe.id, step_number=1, title="Dup", instruction="x")
            )
            await db_session.flush()


async def test_duplicate_blog_slug_is_rejected(db_session: AsyncSession) -> None:
    first, second = build_recipe(), build_recipe()
    db_session.add_all([first, second])
    await db_session.flush()
    slug = f"how-to-make-aloo-posto-{uuid.uuid4().hex}"
    db_session.add(Blog(recipe_id=first.id, title="A", slug=slug))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_blogs_slug"):
        async with db_session.begin_nested():
            db_session.add(Blog(recipe_id=second.id, title="B", slug=slug))
            await db_session.flush()


async def test_one_blog_per_recipe(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()
    db_session.add(Blog(recipe_id=recipe.id, title="A", slug=f"a-{uuid.uuid4().hex}"))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_blogs_recipe_id"):
        async with db_session.begin_nested():
            db_session.add(Blog(recipe_id=recipe.id, title="B", slug=f"b-{uuid.uuid4().hex}"))
            await db_session.flush()


async def test_duplicate_ingredient_image_is_rejected(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()
    ingredient_id = recipe.ingredients[0].id

    def image() -> IngredientImage:
        return IngredientImage(
            recipe_id=recipe.id,
            ingredient_id=ingredient_id,
            image_url="https://example.test/x.jpg",
            provider="wikimedia",
        )

    db_session.add(image())
    await db_session.flush()
    with pytest.raises(IntegrityError, match="uq_ingredient_images_ingredient_id"):
        async with db_session.begin_nested():
            db_session.add(image())
            await db_session.flush()


async def test_one_step_image_per_photo(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()
    photo = await add_media(db_session, recipe)
    db_session.add(StepImage(recipe_id=recipe.id, media_asset_id=photo.id))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_step_images_media_asset_id"):
        async with db_session.begin_nested():
            db_session.add(StepImage(recipe_id=recipe.id, media_asset_id=photo.id))
            await db_session.flush()


async def test_job_progress_must_be_between_0_and_100(db_session: AsyncSession) -> None:
    recipe = build_recipe()
    db_session.add(recipe)
    await db_session.flush()

    with pytest.raises(IntegrityError, match="ck_jobs_progress_range"):
        async with db_session.begin_nested():
            db_session.add(Job(recipe_id=recipe.id, progress=101))
            await db_session.flush()
