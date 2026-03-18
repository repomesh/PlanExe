"""Tests for _patch_schema_for_strict() in responses_api_llm.py"""
import pytest
from typing import Optional, List
from pydantic import BaseModel, Field
from typing import Literal

from worker_plan_internal.llm_util.responses_api_llm import _patch_schema_for_strict


class SimpleModel(BaseModel):
    name: str
    count: int

class ModelWithOptional(BaseModel):
    name: str
    description: Optional[str] = None

class NestedModel(BaseModel):
    label: str

class ModelWithOptionalNested(BaseModel):
    name: str
    nested: Optional[NestedModel] = None

class ModelWithOptionalList(BaseModel):
    name: str
    tags: Optional[List[str]] = None

class ModelWithLiteral(BaseModel):
    name: str
    severity: Literal["low", "medium", "high"]

class ModelWithMixedOptionals(BaseModel):
    """Mimics FailureModeItem from premortem.py"""
    name: str = Field(description="Name")
    owner: Optional[str] = Field(None, description="Owner")
    likelihood: Optional[int] = Field(None, description="1-5")
    tags: Optional[List[str]] = Field(None, description="Tags")


def _check_all_objects_strict(schema: dict) -> None:
    """Recursively verify every object has additionalProperties: false and required."""
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, (
            f"Missing additionalProperties:false in {schema}"
        )
        if "properties" in schema:
            assert "required" in schema, f"Missing required in {schema}"
            assert sorted(schema["required"]) == sorted(schema["properties"].keys())
    for v in schema.get("properties", {}).values():
        _check_all_objects_strict(v)
    if "items" in schema:
        _check_all_objects_strict(schema["items"])
    for key in ("$defs", ):
        if key in schema:
            for v in schema[key].values():
                _check_all_objects_strict(v)
    for combiner in ("anyOf", "oneOf", "allOf"):
        if combiner in schema:
            for sub in schema[combiner]:
                _check_all_objects_strict(sub)


def test_simple_model():
    schema = SimpleModel.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    assert patched["additionalProperties"] is False
    assert "required" in patched
    _check_all_objects_strict(patched)


def test_optional_string():
    schema = ModelWithOptional.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    _check_all_objects_strict(patched)
    # description field should be in required (strict mode)
    assert "description" in patched["required"]


def test_optional_nested_model():
    schema = ModelWithOptionalNested.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    _check_all_objects_strict(patched)


def test_optional_list():
    schema = ModelWithOptionalList.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    _check_all_objects_strict(patched)


def test_literal_no_defs():
    """Literal fields should NOT generate $defs/$ref."""
    schema = ModelWithLiteral.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    assert "$defs" not in patched
    _check_all_objects_strict(patched)


def test_mixed_optionals_like_premortem():
    schema = ModelWithMixedOptionals.model_json_schema()
    patched = _patch_schema_for_strict(schema)
    _check_all_objects_strict(patched)
    # All 4 fields must be in required
    assert len(patched["required"]) == 4
