"""Regex-based transaction tags for statement import preview (ported from CardQL tags.json)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompiledTagRule:
    tag_name: str
    compiled: tuple[re.Pattern[str], ...]


def compile_tag_rules(
    rules: list[tuple[str, list[str]]],
) -> list[CompiledTagRule]:
    """Compile (tag_name, regex_patterns) into case-insensitive patterns."""
    out: list[CompiledTagRule] = []
    for tag_name, patterns in rules:
        compiled = tuple(re.compile(p, re.IGNORECASE) for p in patterns if p.strip())
        if compiled:
            out.append(CompiledTagRule(tag_name=tag_name, compiled=compiled))
    return out


def compute_tags(description: str, rules: list[CompiledTagRule]) -> str:
    """Return space-separated tag names whose patterns match the description."""
    matched: list[str] = []
    for rule in rules:
        if any(p.search(description) for p in rule.compiled):
            matched.append(rule.tag_name)
    return " ".join(matched)
