"""Listing quality rules: one traffic light per element, per ASIN (R1).

Pure module: no database, no network. Thresholds come from ``RuleConfig`` so
they can be overridden per organisation, marketplace and product type (see
``rule_config.resolve_rule_configs``). A light is grey whenever the element
could not be verified; it is never green by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from app.services.catalog_monitor.content import ListingContent
from app.services.catalog_monitor.images import ImageAnalysis

State = Literal["green", "yellow", "red", "grey"]

RULE_KEYS = (
    "title",
    "item_highlights",
    "bullets",
    "description",
    "images",
    "main_image",
    "video",
    "aplus",
    "backend_keywords",
    "attributes",
    "category",
)

_SCORE_POINTS = {"green": 1.0, "yellow": 0.5, "red": 0.0}


@dataclass(frozen=True)
class RuleConfig:
    key: str
    enabled: bool
    mandatory: bool
    params: dict


def _cfg(key: str, mandatory: bool, **params: Any) -> RuleConfig:
    return RuleConfig(key=key, enabled=True, mandatory=mandatory, params=params)


DEFAULT_RULES: dict[str, RuleConfig] = {
    c.key: c
    for c in (
        _cfg("title", True, max_length=75, hard_max_length=200),
        _cfg("item_highlights", False, max_length=125),
        _cfg("bullets", True, target_count=5, min_count=3),
        _cfg("description", False, min_length=200),
        _cfg("images", False, target_count=8, min_count=5),
        _cfg("main_image", True, min_fill=0.85),
        _cfg("video", False),
        _cfg("aplus", False, min_modules=4),
        _cfg("backend_keywords", False, max_bytes=250, min_bytes=100),
        _cfg(
            "attributes",
            True,
            recommended_attributes=[
                "color",
                "size",
                "material",
                "item_dimensions",
                "item_weight",
                "age_range_description",
                "number_of_items",
                "included_components",
            ],
        ),
        _cfg("category", True, expected_category_keywords=[]),
    )
}


@dataclass
class RuleContext:
    main_keyword: Optional[str] = None
    required_attributes: Optional[list[str]] = None  # None = schema unavailable
    main_image: Optional[ImageAnalysis] = None


@dataclass
class RuleResult:
    key: str
    state: State
    mandatory: bool
    code: str
    details: dict = field(default_factory=dict)


@dataclass
class ListingEvaluation:
    asin: str
    state: State
    score: int
    results: list[RuleResult]


def _res(state: State, code: str, **details: Any) -> tuple[State, str, dict]:
    return state, code, details


def _has(text: Optional[str], needle: Optional[str]) -> bool:
    return bool(text and needle and needle.casefold() in text.casefold())


def _param(cfg: RuleConfig, name: str) -> Any:
    if name in cfg.params:
        return cfg.params[name]
    return DEFAULT_RULES[cfg.key].params[name]


def _title(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    title = (c.title or "").strip()
    if not title:
        return _res("red", "missing")
    limit, hard = _param(cfg, "max_length"), _param(cfg, "hard_max_length")
    length = len(title)
    keyword_checked = ctx.main_keyword is not None
    brand_checked = bool(c.brand)
    details: dict = {
        "length": length,
        "limit": limit,
        "brand_checked": brand_checked,
        "keyword_checked": keyword_checked,
    }
    if length > hard:
        return _res("red", "too_long", **{**details, "limit": hard})
    issues: list[str] = []
    if length > limit:
        issues.append("too_long")
    if brand_checked and not _has(title, c.brand):
        issues.append("brand_missing")
    if keyword_checked and not _has(title, ctx.main_keyword):
        issues.append("keyword_missing")
    if issues:
        return _res("yellow", issues[0], **{**details, "issues": issues})
    return _res("green", "ok", **details)


def _item_highlights(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if c.item_highlights is None:
        return _res("grey", "not_exposed")
    text = c.item_highlights.strip()
    if not text:
        return _res("yellow", "missing")
    limit = _param(cfg, "max_length")
    if len(text) > limit:
        return _res("yellow", "too_long", length=len(text), limit=limit)
    return _res("green", "ok", length=len(text), limit=limit)


def _bullets(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    bullets = [b for b in c.bullets if b and b.strip()]
    target, minimum = _param(cfg, "target_count"), _param(cfg, "min_count")
    keyword_checked = ctx.main_keyword is not None
    details: dict = {"count": len(bullets), "target": target, "keyword_checked": keyword_checked}
    if len(bullets) < minimum:
        return _res("red", "too_few", **details)
    if len(bullets) < target:
        return _res("yellow", "too_few", **details)
    if keyword_checked and not any(_has(b, ctx.main_keyword) for b in bullets):
        return _res("yellow", "keyword_missing", **details)
    return _res("green", "ok", **details)


def _description(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    text = (c.description or "").strip()
    if not text:
        return _res("red", "missing")
    minimum = _param(cfg, "min_length")
    keyword_checked = ctx.main_keyword is not None
    details: dict = {"length": len(text), "limit": minimum, "keyword_checked": keyword_checked}
    if len(text) < minimum:
        return _res("yellow", "too_short", **details)
    if keyword_checked and not _has(text, ctx.main_keyword):
        return _res("yellow", "keyword_missing", **details)
    return _res("green", "ok", **details)


def _images(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    count = len(c.images)
    target, minimum = _param(cfg, "target_count"), _param(cfg, "min_count")
    details = {"count": count, "target": target}
    if count >= target:
        return _res("green", "ok", **details)
    return _res("yellow" if count >= minimum else "red", "too_few", **details)


def _main_image(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if not c.images or c.images[0].variant != "MAIN":
        return _res("red", "missing")
    analysis = ctx.main_image
    if analysis is None or analysis.error:
        return _res("grey", "analysis_failed", error=analysis.error if analysis else None)
    minimum = _param(cfg, "min_fill")
    details = {
        "fill_ratio": round(analysis.fill_ratio, 2),
        "limit": minimum,
        "text_checked": False,
    }
    if not analysis.white_background:
        return _res("red", "background_not_white", **details)
    if analysis.fill_ratio < minimum:
        return _res("yellow", "low_fill", **details)
    return _res("green", "ok", **details)


def _video(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    return _res("grey", "not_exposed")


def _aplus(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if not c.aplus_available or c.aplus_module_count is None:
        return _res("grey", "unavailable")
    count = c.aplus_module_count
    minimum = _param(cfg, "min_modules")
    if count == 0:
        return _res("red", "missing", modules=0, target=minimum)
    if count < minimum:
        return _res("yellow", "too_few", modules=count, target=minimum)
    return _res("green", "ok", modules=count, target=minimum)


def _backend_keywords(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if not c.backend_keywords_readable:
        return _res("grey", "unavailable")
    text = (c.backend_keywords or "").strip()
    if not text:
        return _res("red", "missing")
    size = len(text.encode("utf-8"))
    maximum, minimum = _param(cfg, "max_bytes"), _param(cfg, "min_bytes")
    if size > maximum:
        return _res("red", "over_limit", bytes=size, limit=maximum)
    if size < minimum:
        return _res("yellow", "too_short", bytes=size, limit=minimum)
    return _res("green", "ok", bytes=size, limit=maximum)


def _attributes(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if ctx.required_attributes is None:
        return _res("grey", "unavailable")

    def present(name: str) -> bool:
        for item in c.attributes.get(name) or []:
            value = item.get("value") if isinstance(item, dict) else item
            if value not in (None, "", [], {}) and not (
                isinstance(value, str) and not value.strip()
            ):
                return True
        return False

    missing_required = [a for a in ctx.required_attributes if not present(a)]
    if missing_required:
        return _res("red", "required_missing", missing=missing_required)
    missing_recommended = [
        a for a in _param(cfg, "recommended_attributes") if not present(a)
    ]
    if missing_recommended:
        return _res("yellow", "recommended_missing", missing=missing_recommended)
    return _res("green", "ok")


def _category(c: ListingContent, ctx: RuleContext, cfg: RuleConfig):
    if not c.classification_path:
        return _res("red", "missing")
    path = " > ".join(c.classification_path)
    expected = [k for k in _param(cfg, "expected_category_keywords") if k]
    if expected and not any(k.casefold() in path.casefold() for k in expected):
        return _res("red", "mismatch", path=path, expected=expected)
    return _res("green", "ok", path=path)


_EVALUATORS: dict[str, Callable[[ListingContent, RuleContext, RuleConfig], tuple]] = {
    "title": _title,
    "item_highlights": _item_highlights,
    "bullets": _bullets,
    "description": _description,
    "images": _images,
    "main_image": _main_image,
    "video": _video,
    "aplus": _aplus,
    "backend_keywords": _backend_keywords,
    "attributes": _attributes,
    "category": _category,
}


def _overall(results: list[RuleResult]) -> tuple[State, int]:
    scored = [r for r in results if r.state != "grey"]
    if not scored:
        return "grey", 0
    if any(r.state == "red" and r.mandatory for r in scored):
        state: State = "red"
    elif any(r.state in ("red", "yellow") for r in scored):
        state = "yellow"
    else:
        state = "green"
    weight = lambda r: 2 if r.mandatory else 1  # noqa: E731
    total = sum(weight(r) for r in scored)
    got = sum(weight(r) * _SCORE_POINTS[r.state] for r in scored)
    return state, int(100 * got / total + 0.5)


def evaluate_listing(
    content: ListingContent,
    ctx: RuleContext,
    configs: Optional[dict[str, RuleConfig]] = None,
) -> ListingEvaluation:
    configs = configs if configs is not None else DEFAULT_RULES
    results: list[RuleResult] = []
    for key in RULE_KEYS:
        cfg = configs.get(key)
        if cfg is None or not cfg.enabled:
            continue
        state, code, details = _EVALUATORS[key](content, ctx, cfg)
        results.append(RuleResult(key, state, cfg.mandatory, code, details))
    state, score = _overall(results)
    return ListingEvaluation(content.asin, state, score, results)


def evaluation_to_dict(ev: ListingEvaluation) -> dict:
    return {
        "asin": ev.asin,
        "state": ev.state,
        "score": ev.score,
        "results": [
            {
                "key": r.key,
                "state": r.state,
                "mandatory": r.mandatory,
                "code": r.code,
                "details": r.details,
            }
            for r in ev.results
        ],
    }
