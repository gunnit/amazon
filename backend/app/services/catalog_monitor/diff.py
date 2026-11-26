"""Field-by-field content diff and variation-family diff (R2, R3).

Pure module: no database, no network. ``diff_content`` compares brand-approved
content with live content; ``diff_family`` compares a stored variation family
with the live one. Values in the results are JSON-serialisable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.services.catalog_monitor.content import VOLATILE_ATTRIBUTES, ListingContent

# Covered by the dedicated fields; reporting them again would double every edit.
_COVERED_ATTRIBUTES = frozenset(
    {"item_name", "bullet_point", "product_description", "generic_keyword"}
)
_DROPPED_KEYS = frozenset({"language_tag", "marketplace_id"})


@dataclass
class FieldChange:
    field: str
    change: Literal["modified", "missing", "added", "reordered"]
    baseline: Any
    live: Any


@dataclass
class VariationFinding:
    kind: Literal["child_detached", "family_broken", "unexpected_child", "theme_changed"]
    parent_asin: str
    child_asin: Optional[str]
    baseline: Any
    live: Any


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _norm_leaf(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, dict):
        return {k: _norm_leaf(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm_leaf(v) for v in value]
    return value


def _text_change(name: str, baseline: Optional[str], live: Optional[str]) -> list[FieldChange]:
    base, now = _norm(baseline), _norm(live)
    if not base or base == now:
        return []
    return [FieldChange(name, "missing" if not now else "modified", base, now)]


def _list_change(name: str, baseline: list[str], live: list[str]) -> list[FieldChange]:
    if not baseline or baseline == live:
        return []
    if not live:
        change = "missing"
    elif sorted(baseline) == sorted(live):
        change = "reordered"
    else:
        change = "modified"
    return [FieldChange(name, change, baseline, live)]


def _attribute_values(content: ListingContent, name: str) -> list[Any]:
    out: list[Any] = []
    for entry in content.attributes.get(name) or []:
        if not isinstance(entry, dict):
            continue
        mp = entry.get("marketplace_id")
        if mp and mp != content.marketplace_id:
            continue
        out.append(
            {k: _norm_leaf(v) for k, v in entry.items() if k not in _DROPPED_KEYS}
        )
    return out


def diff_content(baseline: ListingContent, live: ListingContent) -> list[FieldChange]:
    changes: list[FieldChange] = []
    changes += _text_change("title", baseline.title, live.title)
    changes += _list_change(
        "bullets",
        [_norm(b) for b in baseline.bullets if _norm(b)],
        [_norm(b) for b in live.bullets if _norm(b)],
    )
    changes += _text_change("description", baseline.description, live.description)
    changes += _list_change(
        "images", [i.url for i in baseline.images], [i.url for i in live.images]
    )
    if (
        baseline.aplus_available
        and live.aplus_available
        and baseline.aplus_module_count is not None
        and live.aplus_module_count is not None
        and baseline.aplus_module_count != live.aplus_module_count
    ):
        change = (
            "missing"
            if baseline.aplus_module_count > 0 and live.aplus_module_count == 0
            else "modified"
        )
        changes.append(
            FieldChange("aplus", change, baseline.aplus_module_count, live.aplus_module_count)
        )
    skip = VOLATILE_ATTRIBUTES | _COVERED_ATTRIBUTES
    for name in sorted(baseline.attributes):
        if name in skip or name.startswith("main_product_image") or name.startswith(
            "other_product_image"
        ) or name == "swatch_product_image":
            continue
        base_vals = _attribute_values(baseline, name)
        if not base_vals:
            continue
        live_vals = _attribute_values(live, name)
        if base_vals == live_vals:
            continue
        changes.append(
            FieldChange(
                f"attribute:{name}", "modified" if live_vals else "missing", base_vals, live_vals
            )
        )
    return changes


def diff_family(
    parent_asin: str,
    baseline_theme: Optional[str],
    baseline_children: list[str],
    live_parent: Optional[ListingContent],
    live_children: dict[str, Optional[ListingContent]],
    *,
    is_partial: bool = False,
) -> list[VariationFinding]:
    findings: list[VariationFinding] = []
    broken = (
        live_parent is not None
        and not live_parent.child_asins
        and bool(baseline_children)
    )
    if broken:
        findings.append(
            VariationFinding("family_broken", parent_asin, None, baseline_children, [])
        )
    else:
        for asin in baseline_children:
            live = live_children.get(asin)
            if live is not None and parent_asin not in live.parent_asins:
                findings.append(
                    VariationFinding(
                        "child_detached", parent_asin, asin, parent_asin, list(live.parent_asins)
                    )
                )
        if live_parent is not None and not is_partial:
            known = set(baseline_children)
            for asin in live_parent.child_asins:
                if asin not in known:
                    findings.append(
                        VariationFinding("unexpected_child", parent_asin, asin, None, asin)
                    )
    if (
        live_parent is not None
        and (baseline_theme is not None or not is_partial)
        and baseline_theme != live_parent.variation_theme
    ):
        findings.append(
            VariationFinding(
                "theme_changed", parent_asin, None, baseline_theme, live_parent.variation_theme
            )
        )
    return findings
