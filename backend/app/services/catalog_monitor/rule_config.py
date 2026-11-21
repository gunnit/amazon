"""Resolve the effective rule configuration for one marketplace and product type (R1).

Pure module. Overrides come from ``listing_quality_rules``; any object with
``marketplace_id``, ``product_type``, ``rule_key``, ``enabled``, ``mandatory`` and
``params`` works. For each rule the most specific matching override wins as a whole
(marketplace + product type, then product type, then marketplace, then the
organisation default); its params are merged over the code defaults.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.services.catalog_monitor.rules import DEFAULT_RULES, RuleConfig


def _specificity(
    override, marketplace_id: str, product_type: Optional[str]
) -> Optional[int]:
    mp, pt = override.marketplace_id, override.product_type
    if mp is not None and mp != marketplace_id:
        return None
    if pt is not None and pt != product_type:
        return None
    return (2 if pt is not None else 0) + (1 if mp is not None else 0)


def resolve_rule_configs(
    overrides: Iterable, marketplace_id: str, product_type: Optional[str]
) -> dict[str, RuleConfig]:
    best: dict[str, tuple[int, object]] = {}
    for o in overrides:
        if o.rule_key not in DEFAULT_RULES:
            continue
        rank = _specificity(o, marketplace_id, product_type)
        if rank is None:
            continue
        current = best.get(o.rule_key)
        if current is None or rank > current[0]:
            best[o.rule_key] = (rank, o)
    resolved: dict[str, RuleConfig] = {}
    for key, default in DEFAULT_RULES.items():
        if key not in best:
            resolved[key] = default
            continue
        o = best[key][1]
        resolved[key] = RuleConfig(
            key=key,
            enabled=bool(o.enabled),
            mandatory=bool(o.mandatory),
            params={**default.params, **(o.params or {})},
        )
    return resolved
