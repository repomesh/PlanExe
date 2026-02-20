"""Helpers for filtering LLM config entries by provider class."""

from __future__ import annotations

from typing import Optional

ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES = "PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES"


def parse_llm_class_whitelist(raw_value: Optional[str]) -> Optional[set[str]]:
    """
    Parse a comma-separated whitelist string into normalized class names.

    Returns None when unset/blank, meaning no filtering is applied.
    """
    if not isinstance(raw_value, str):
        return None
    parts = [item.strip() for item in raw_value.split(",")]
    normalized = {item.lower() for item in parts if item}
    if not normalized:
        return None
    return normalized


def is_llm_class_allowed(class_name: Optional[str], whitelist: Optional[set[str]]) -> bool:
    """
    Return True when a class name is allowed by the whitelist.

    If whitelist is None, everything is allowed.
    """
    if whitelist is None:
        return True
    if not isinstance(class_name, str):
        return False
    return class_name.strip().lower() in whitelist
