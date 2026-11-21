from types import SimpleNamespace

from app.services.catalog_monitor.content import ImageRef, ListingContent
from app.services.catalog_monitor.images import ImageAnalysis
from app.services.catalog_monitor.rule_config import resolve_rule_configs
from app.services.catalog_monitor.rules import (
    DEFAULT_RULES,
    RULE_KEYS,
    RuleConfig,
    RuleContext,
    evaluate_listing,
    evaluation_to_dict,
)

MP = "APJ6JRA9NG5V4"


def imgs(n):
    out = [ImageRef("MAIN", "https://x/0.jpg")] if n else []
    return out + [ImageRef(f"PT0{i}", f"https://x/{i}.jpg") for i in range(1, n)]


def good(**kw):
    base = dict(
        asin="B0TEST0001",
        marketplace_id=MP,
        title="TESTBRAND widget blu",
        brand="TESTBRAND",
        bullets=["widget uno", "due", "tre", "quattro", "cinque"],
        description="widget " + "x" * 220,
        item_highlights="breve",
        backend_keywords="k" * 120,
        backend_keywords_readable=True,
        images=imgs(8),
        aplus_available=True,
        aplus_module_count=4,
        attributes={"color": [{"value": "blu"}]},
        classification_path=["Casa", "Cucina"],
    )
    base.update(kw)
    return ListingContent(**base)


OK_IMG = ImageAnalysis(True, 0.9, 1000, 1000)


def ctx(**kw):
    base = dict(main_keyword="widget", required_attributes=["color"], main_image=OK_IMG)
    base.update(kw)
    return RuleContext(**base)


def res(content, c, key):
    ev = evaluate_listing(content, c)
    return next(r for r in ev.results if r.key == key)


def test_title_75_is_green_76_is_yellow_201_is_red():
    pad = lambda n: ("TESTBRAND widget " + "a" * n)[:n]  # noqa: E731
    assert res(good(title=pad(75)), ctx(), "title").state == "green"
    r76 = res(good(title=pad(76)), ctx(), "title")
    assert (r76.state, r76.code) == ("yellow", "too_long")
    assert res(good(title=pad(200)), ctx(), "title").state == "yellow"
    r201 = res(good(title=pad(201)), ctx(), "title")
    assert (r201.state, r201.code) == ("red", "too_long")
    assert res(good(title=None), ctx(), "title").code == "missing"


def test_title_without_brand_is_yellow():
    r = res(good(title="widget blu"), ctx(), "title")
    assert (r.state, r.code) == ("yellow", "brand_missing")


def test_title_without_keyword_is_yellow_and_issues_listed():
    r = res(good(title="TESTBRAND blu " + "a" * 70), ctx(), "title")
    assert r.state == "yellow" and r.code == "too_long"
    assert r.details["issues"] == ["too_long", "keyword_missing"]


def test_title_is_case_insensitive():
    assert res(good(title="testbrand WIDGET"), ctx(), "title").state == "green"


def test_title_keyword_check_skipped_when_unknown():
    r = res(good(title="TESTBRAND blu"), ctx(main_keyword=None), "title")
    assert r.state == "green" and r.details["keyword_checked"] is False


def test_item_highlights():
    assert res(good(item_highlights=None), ctx(), "item_highlights").state == "grey"
    assert res(good(item_highlights="a" * 125), ctx(), "item_highlights").state == "green"
    assert res(good(item_highlights="a" * 126), ctx(), "item_highlights").state == "yellow"


def test_bullets_5_green_4_yellow_2_red():
    b = lambda n: [f"widget {i}" for i in range(n)]  # noqa: E731
    assert res(good(bullets=b(5)), ctx(), "bullets").state == "green"
    assert res(good(bullets=b(3)), ctx(), "bullets").state == "yellow"
    assert res(good(bullets=b(4)), ctx(), "bullets").state == "yellow"
    assert res(good(bullets=b(2)), ctx(), "bullets").state == "red"
    assert res(good(bullets=[]), ctx(), "bullets").state == "red"


def test_bullets_keyword_missing_is_yellow_unless_unknown():
    five = ["a", "b", "c", "d", "e"]
    r = res(good(bullets=five), ctx(), "bullets")
    assert (r.state, r.code) == ("yellow", "keyword_missing")
    assert res(good(bullets=five), ctx(main_keyword=None), "bullets").state == "green"


def test_description():
    assert res(good(description=None), ctx(), "description").state == "red"
    assert res(good(description="widget short"), ctx(), "description").code == "too_short"
    assert res(good(description="x" * 250), ctx(), "description").code == "keyword_missing"
    assert res(good(), ctx(), "description").state == "green"


def test_images_8_green_6_yellow_4_red():
    assert res(good(images=imgs(8)), ctx(), "images").state == "green"
    assert res(good(images=imgs(6)), ctx(), "images").state == "yellow"
    assert res(good(images=imgs(5)), ctx(), "images").state == "yellow"
    assert res(good(images=imgs(4)), ctx(), "images").state == "red"


def test_main_image_grey_when_analysis_missing():
    assert res(good(), ctx(main_image=None), "main_image").state == "grey"
    bad = ImageAnalysis(False, 0.0, 0, 0, error="download failed")
    r = res(good(), ctx(main_image=bad), "main_image")
    assert (r.state, r.code) == ("grey", "analysis_failed")


def test_main_image_red_when_background_not_white():
    c = ctx(main_image=ImageAnalysis(False, 0.9, 1000, 1000))
    r = res(good(), c, "main_image")
    assert (r.state, r.code) == ("red", "background_not_white")


def test_main_image_missing_or_not_main_is_red():
    assert res(good(images=[]), ctx(), "main_image").code == "missing"
    other = [ImageRef("PT01", "https://x/1.jpg")]
    assert res(good(images=other), ctx(), "main_image").state == "red"


def test_main_image_fill_and_details():
    r = res(good(), ctx(main_image=ImageAnalysis(True, 0.8449, 10, 10)), "main_image")
    assert (r.state, r.code) == ("yellow", "low_fill")
    assert r.details["fill_ratio"] == 0.84 and r.details["text_checked"] is False
    assert res(good(), ctx(main_image=ImageAnalysis(True, 0.85, 10, 10)), "main_image").state == "green"


def test_video_always_grey():
    assert res(good(has_video=True), ctx(), "video").state == "grey"
    assert res(good(has_video=None), ctx(), "video").state == "grey"


def test_aplus_grey_when_api_unavailable():
    assert res(good(aplus_available=False), ctx(), "aplus").state == "grey"
    assert res(good(aplus_module_count=None), ctx(), "aplus").state == "grey"
    assert res(good(aplus_module_count=0), ctx(), "aplus").state == "red"
    assert res(good(aplus_module_count=3), ctx(), "aplus").state == "yellow"
    assert res(good(aplus_module_count=4), ctx(), "aplus").state == "green"


def test_backend_keywords_251_bytes_red_counts_utf8_bytes():
    r = res(good(backend_keywords="è" * 126), ctx(), "backend_keywords")  # 252 bytes
    assert (r.state, r.code) == ("red", "over_limit")
    assert r.details["bytes"] == 252
    assert res(good(backend_keywords="è" * 125), ctx(), "backend_keywords").state == "green"
    assert res(good(backend_keywords="k" * 251), ctx(), "backend_keywords").state == "red"
    assert res(good(backend_keywords="k" * 99), ctx(), "backend_keywords").state == "yellow"
    assert res(good(backend_keywords=None), ctx(), "backend_keywords").code == "missing"


def test_backend_keywords_grey_when_not_readable():
    r = res(good(backend_keywords_readable=False, backend_keywords=None), ctx(), "backend_keywords")
    assert r.state == "grey"


def test_attributes_grey_without_schema():
    assert res(good(), ctx(required_attributes=None), "attributes").state == "grey"


def test_attributes_red_when_required_missing():
    r = res(good(), ctx(required_attributes=["color", "voltage"]), "attributes")
    assert (r.state, r.code) == ("red", "required_missing")
    assert r.details["missing"] == ["voltage"]
    empty = good(attributes={"color": [{"value": "  "}]})
    assert res(empty, ctx(), "attributes").state == "red"


def test_attributes_yellow_when_recommended_missing_green_when_complete():
    assert res(good(), ctx(), "attributes").code == "recommended_missing"
    full = {k: [{"value": "v"}] for k in DEFAULT_RULES["attributes"].params["recommended_attributes"]}
    assert res(good(attributes=full), ctx(), "attributes").state == "green"


def test_category_rules():
    assert res(good(classification_path=[]), ctx(), "category").state == "red"
    assert res(good(), ctx(), "category").state == "green"
    cfg = {**DEFAULT_RULES, "category": RuleConfig("category", True, True, {"expected_category_keywords": ["giardino"]})}
    ev = evaluate_listing(good(), ctx(), cfg)
    r = next(x for x in ev.results if x.key == "category")
    assert (r.state, r.code) == ("red", "mismatch")
    ev2 = evaluate_listing(good(classification_path=["Giardino e giardinaggio"]), ctx(), cfg)
    assert next(x for x in ev2.results if x.key == "category").state == "green"


def test_perfect_listing_is_green_with_score_100_except_attributes():
    full = {k: [{"value": "v"}] for k in DEFAULT_RULES["attributes"].params["recommended_attributes"]}
    ev = evaluate_listing(good(attributes=full), ctx())
    # video is grey; everything else green
    assert ev.state == "green" and ev.score == 100
    assert [r.key for r in ev.results] == list(RULE_KEYS)


def test_overall_red_only_from_mandatory():
    ev = evaluate_listing(good(images=imgs(2)), ctx())  # images red, non-mandatory
    assert next(r for r in ev.results if r.key == "images").state == "red"
    assert ev.state == "yellow"
    ev2 = evaluate_listing(good(bullets=[]), ctx())  # bullets red, mandatory
    assert ev2.state == "red"


def test_overall_grey_when_all_grey():
    cfg = {k: v for k, v in DEFAULT_RULES.items() if k in ("video", "item_highlights")}
    ev = evaluate_listing(good(item_highlights=None), ctx(), cfg)
    assert ev.state == "grey" and ev.score == 0


def test_score_weights_mandatory_double():
    cfg = {
        "title": RuleConfig("title", True, True, DEFAULT_RULES["title"].params),
        "images": RuleConfig("images", True, False, DEFAULT_RULES["images"].params),
    }
    # title green (weight 2), images red (weight 1): 2/3
    ev = evaluate_listing(good(images=imgs(1)), ctx(), cfg)
    assert ev.score == 67
    # title yellow (0.5*2) + images green (1) = 2/3 as well
    ev = evaluate_listing(good(title="widget blu"), ctx(), cfg)
    assert ev.score == 67
    # same states, mandatory flipped: images weighs 2, title 1
    cfg2 = {**cfg, "title": RuleConfig("title", True, False, cfg["title"].params),
            "images": RuleConfig("images", True, True, cfg["images"].params)}
    assert evaluate_listing(good(images=imgs(1)), ctx(), cfg2).score == 33


def test_disabled_rule_is_omitted():
    cfg = {**DEFAULT_RULES, "video": RuleConfig("video", False, False, {})}
    ev = evaluate_listing(good(), ctx(), cfg)
    assert "video" not in [r.key for r in ev.results]


def test_evaluation_to_dict_is_json_serialisable():
    import json

    d = evaluation_to_dict(evaluate_listing(good(), ctx()))
    json.dumps(d)
    assert d["asin"] == "B0TEST0001" and d["results"][0]["key"] == "title"


def ov(rule_key, mp=None, pt=None, enabled=True, mandatory=False, params=None):
    return SimpleNamespace(marketplace_id=mp, product_type=pt, rule_key=rule_key,
                           enabled=enabled, mandatory=mandatory, params=params)


def test_resolve_defaults_without_overrides():
    assert resolve_rule_configs([], MP, "TOY") == DEFAULT_RULES


def test_override_most_specific_wins():
    rows = [
        ov("title", params={"max_length": 70}),
        ov("title", mp=MP, params={"max_length": 60}),
        ov("title", pt="TOY", params={"max_length": 50}),
    ]
    get = lambda mp, pt: resolve_rule_configs(rows, mp, pt)["title"].params["max_length"]  # noqa: E731
    assert get("OTHER", "SHOES") == 70
    assert get(MP, "SHOES") == 60
    assert get("OTHER", "TOY") == 50
    assert get(MP, "TOY") == 50  # product type beats marketplace
    rows.append(ov("title", mp=MP, pt="TOY", params={"max_length": 40}))
    assert get(MP, "TOY") == 40
    assert get("OTHER", None) == 70
    # unmerged params fall back to code defaults
    assert resolve_rule_configs(rows, MP, "TOY")["title"].params["hard_max_length"] == 200


def test_override_can_disable_rule():
    cfg = resolve_rule_configs([ov("video", enabled=False)], MP, None)
    assert cfg["video"].enabled is False
    assert "video" not in [r.key for r in evaluate_listing(good(), ctx(), cfg).results]


def test_override_can_change_mandatory_and_ignores_unknown_keys():
    cfg = resolve_rule_configs([ov("images", mandatory=True), ov("bogus")], MP, None)
    assert cfg["images"].mandatory is True and "bogus" not in cfg
