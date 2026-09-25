"""initial schema

Creates every table the application needs (SPEC §8 plus the extra columns later
modules rely on). Hand-reviewed from an autogenerate draft:
- PostgreSQL enum types are created/dropped explicitly (`language` is shared by two columns).
- The recipes.hero_media_id -> media_assets FK is circular, so it is added after both tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

language = postgresql.ENUM("auto", "en", "bn", "hi", name="language", create_type=False)
recipe_status = postgresql.ENUM(
    "UPLOADED", "QUEUED", "PROCESSING", "TRANSCRIBING", "EXTRACTING", "FETCHING_IMAGES",
    "MATCHING_IMAGES", "GENERATING_BLOG", "COMPLETED", "FAILED",
    name="recipe_status", create_type=False,
)
job_status = postgresql.ENUM(
    "QUEUED", "RUNNING", "COMPLETED", "FAILED", name="job_status", create_type=False
)
job_step = postgresql.ENUM(
    "UPLOADED", "QUEUED", "PROCESSING", "TRANSCRIBING", "EXTRACTING", "FETCHING_IMAGES",
    "MATCHING_IMAGES", "GENERATING_BLOG", "COMPLETED",
    name="job_step", create_type=False,
)
media_type = postgresql.ENUM(
    "audio", "video", "hero_image", "cooking_image", "ingredient_image",
    name="media_type", create_type=False,
)
blog_status = postgresql.ENUM("DRAFT", "PUBLISHED", name="blog_status", create_type=False)
step_image_status = postgresql.ENUM(
    "MATCHED", "UNMATCHED", "MANUAL", name="step_image_status", create_type=False
)

ALL_ENUMS = (
    language, recipe_status, job_status, job_step, media_type, blog_status, step_image_status
)


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _recipe_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["recipe_id"], ["recipes.id"], name=f"fk_{table}_recipe_id_recipes", ondelete="CASCADE"
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=False)

    op.create_table(
        "recipes",
        _id(),
        sa.Column("title", sa.String(300)),
        sa.Column("slug", sa.String(200)),
        sa.Column("language", language, server_default="auto", nullable=False),
        sa.Column("detected_language", language),
        sa.Column("status", recipe_status, server_default="UPLOADED", nullable=False),
        sa.Column("transcript", sa.Text()),
        sa.Column("dish_name", sa.String(300)),
        sa.Column("description", sa.Text()),
        sa.Column("instructions", sa.Text()),
        sa.Column("cuisine", sa.String(100)),
        sa.Column("category", sa.String(100)),
        sa.Column(
            "keywords", sa.ARRAY(sa.String(100)), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("hero_media_id", sa.Uuid()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("owner_id", sa.String(255)),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_recipes"),
        sa.UniqueConstraint("slug", name="uq_recipes_slug"),
    )
    op.create_index("ix_recipes_status", "recipes", ["status"])
    op.create_index("ix_recipes_owner_id", "recipes", ["owner_id"])

    op.create_table(
        "media_assets",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("type", media_type, nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer()),
        _timestamp("created_at"),
        _recipe_fk("media_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
    )
    op.create_index("ix_media_assets_recipe_id_type", "media_assets", ["recipe_id", "type"])

    # Circular reference: recipes.hero_media_id -> media_assets.id
    op.create_foreign_key(
        "fk_recipes_hero_media_id_media_assets",
        "recipes",
        "media_assets",
        ["hero_media_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "ingredients",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.String(100)),
        sa.Column("unit", sa.String(50)),
        sa.Column("notes", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        _recipe_fk("ingredients"),
        sa.PrimaryKeyConstraint("id", name="pk_ingredients"),
        sa.UniqueConstraint("recipe_id", "position", name="uq_ingredients_recipe_id_position"),
    )
    op.create_index("ix_ingredients_recipe_id", "ingredients", ["recipe_id"])

    op.create_table(
        "recipe_steps",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("duration", sa.String(100)),
        sa.Column("temperature", sa.String(100)),
        _recipe_fk("recipe_steps"),
        sa.PrimaryKeyConstraint("id", name="pk_recipe_steps"),
        sa.UniqueConstraint(
            "recipe_id", "step_number", name="uq_recipe_steps_recipe_id_step_number"
        ),
    )
    op.create_index("ix_recipe_steps_recipe_id", "recipe_steps", ["recipe_id"])

    op.create_table(
        "cooking_suggestions",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        _recipe_fk("cooking_suggestions"),
        sa.PrimaryKeyConstraint("id", name="pk_cooking_suggestions"),
        sa.UniqueConstraint(
            "recipe_id", "position", name="uq_cooking_suggestions_recipe_id_position"
        ),
    )
    op.create_index("ix_cooking_suggestions_recipe_id", "cooking_suggestions", ["recipe_id"])

    op.create_table(
        "step_images",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid()),
        sa.Column("media_asset_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("status", step_image_status, server_default="UNMATCHED", nullable=False),
        sa.Column("reason", sa.Text()),
        _recipe_fk("step_images"),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["recipe_steps.id"],
            name="fk_step_images_step_id_recipe_steps",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name="fk_step_images_media_asset_id_media_assets",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_step_images"),
        sa.UniqueConstraint("media_asset_id", name="uq_step_images_media_asset_id"),
    )
    op.create_index("ix_step_images_recipe_id", "step_images", ["recipe_id"])
    op.create_index("ix_step_images_step_id", "step_images", ["step_id"])

    op.create_table(
        "ingredient_images",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("license", sa.String(200)),
        sa.Column("attribution", sa.Text()),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("alt_text", sa.String(300)),
        _recipe_fk("ingredient_images"),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name="fk_ingredient_images_ingredient_id_ingredients",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_images"),
        sa.UniqueConstraint("ingredient_id", name="uq_ingredient_images_ingredient_id"),
    )
    op.create_index("ix_ingredient_images_recipe_id", "ingredient_images", ["recipe_id"])

    op.create_table(
        "blogs",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("status", blog_status, server_default="DRAFT", nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("meta_title", sa.String(300)),
        sa.Column("meta_description", sa.String(500)),
        sa.Column("content_html", sa.Text()),
        sa.Column("content_markdown", sa.Text()),
        sa.Column("canonical_url", sa.String(500)),
        sa.Column("primary_keyword", sa.String(200)),
        sa.Column(
            "secondary_keywords",
            sa.ARRAY(sa.String(200)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("og_title", sa.String(300)),
        sa.Column("og_description", sa.String(500)),
        sa.Column("hero_alt_text", sa.String(300)),
        sa.Column("json_ld", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("faq", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _recipe_fk("blogs"),
        sa.PrimaryKeyConstraint("id", name="pk_blogs"),
        sa.UniqueConstraint("recipe_id", name="uq_blogs_recipe_id"),
        sa.UniqueConstraint("slug", name="uq_blogs_slug"),
    )

    op.create_table(
        "jobs",
        _id(),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("status", job_status, server_default="QUEUED", nullable=False),
        sa.Column("current_step", job_step, server_default="UPLOADED", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("celery_task_id", sa.String(255)),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_jobs_progress_range"),
        _recipe_fk("jobs"),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_recipe_id", "jobs", ["recipe_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("blogs")
    op.drop_table("ingredient_images")
    op.drop_table("step_images")
    op.drop_table("cooking_suggestions")
    op.drop_table("recipe_steps")
    op.drop_table("ingredients")
    op.drop_constraint("fk_recipes_hero_media_id_media_assets", "recipes", type_="foreignkey")
    op.drop_table("media_assets")
    op.drop_table("recipes")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=False)
