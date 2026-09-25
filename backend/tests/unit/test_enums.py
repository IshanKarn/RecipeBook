import pytest

from app.models.enums import (
    BlogStatus,
    JobStatus,
    Language,
    MediaType,
    RecipeStatus,
    StepImageStatus,
)

pytestmark = pytest.mark.unit


def test_recipe_status_matches_spec_section_9() -> None:
    assert [s.value for s in RecipeStatus] == [
        "UPLOADED",
        "QUEUED",
        "PROCESSING",
        "TRANSCRIBING",
        "EXTRACTING",
        "FETCHING_IMAGES",
        "MATCHING_IMAGES",
        "GENERATING_BLOG",
        "COMPLETED",
        "FAILED",
    ]


def test_media_types_match_spec_section_8() -> None:
    assert {m.value for m in MediaType} == {
        "audio",
        "video",
        "hero_image",
        "cooking_image",
        "ingredient_image",
    }


def test_languages_match_spec_section_5() -> None:
    assert [lang.value for lang in Language] == ["auto", "en", "bn", "hi"]


def test_small_enums() -> None:
    assert [s.value for s in JobStatus] == ["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    assert [s.value for s in BlogStatus] == ["DRAFT", "PUBLISHED"]
    assert [s.value for s in StepImageStatus] == ["MATCHED", "UNMATCHED", "MANUAL"]
