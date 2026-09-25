"""Domain enums shared by models, schemas and services."""

from enum import StrEnum


class RecipeStatus(StrEnum):
    """Lifecycle of a recipe (SPEC §9)."""

    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    EXTRACTING = "EXTRACTING"
    FETCHING_IMAGES = "FETCHING_IMAGES"
    MATCHING_IMAGES = "MATCHING_IMAGES"
    GENERATING_BLOG = "GENERATING_BLOG"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStep(StrEnum):
    """Which processing stage a job is on. Failure is carried by `JobStatus.FAILED`."""

    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    EXTRACTING = "EXTRACTING"
    FETCHING_IMAGES = "FETCHING_IMAGES"
    MATCHING_IMAGES = "MATCHING_IMAGES"
    GENERATING_BLOG = "GENERATING_BLOG"
    COMPLETED = "COMPLETED"


class MediaType(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    HERO_IMAGE = "hero_image"
    COOKING_IMAGE = "cooking_image"
    INGREDIENT_IMAGE = "ingredient_image"


class Language(StrEnum):
    AUTO = "auto"
    EN = "en"
    BN = "bn"
    HI = "hi"


class BlogStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class StepImageStatus(StrEnum):
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    MANUAL = "MANUAL"
