from app.services.catalog_monitor.content import ImageRef, ListingContent
from app.services.catalog_monitor.diff import diff_content, diff_family

MP = "APJ6JRA9NG5V4"


def make(asin="B0TEST0001", **kw) -> ListingContent:
    return ListingContent(asin=asin, marketplace_id=MP, **kw)


def attr(value, mp=MP):
    return [{"value": value, "language_tag": "it_IT", "marketplace_id": mp}]


def imgs(*urls):
    return [ImageRef("MAIN" if i == 0 else f"PT0{i}", u) for i, u in enumerate(urls)]


def by_field(changes):
    return {c.field: c for c in changes}


def test_identical_content_has_no_changes():
    base = make(title="T", bullets=["a", "b"], description="d", images=imgs("u1", "u2"))
    live = make(title="T", bullets=["a", "b"], description="d", images=imgs("u1", "u2"))
    assert diff_content(base, live) == []


def test_whitespace_only_change_is_not_a_change():
    base = make(title="Hello world", bullets=["one two"], description="a b")
    live = make(title="  Hello   world ", bullets=["one\n two"], description="a  b\n")
    assert diff_content(base, live) == []


def test_title_modified_and_missing():
    c = diff_content(make(title="Old"), make(title="New"))
    assert (c[0].field, c[0].change, c[0].baseline, c[0].live) == ("title", "modified", "Old", "New")
    c = diff_content(make(title="Old"), make(title=None))
    assert c[0].change == "missing"


def test_bullets_reordered_modified_missing():
    base = make(bullets=["a", "b", "c"])
    assert diff_content(base, make(bullets=["c", "a", "b"]))[0].change == "reordered"
    assert diff_content(base, make(bullets=["a", "b", "x"]))[0].change == "modified"
    c = diff_content(base, make(bullets=[]))[0]
    assert (c.field, c.change, c.live) == ("bullets", "missing", [])


def test_description_modified():
    c = diff_content(make(description="x"), make(description="y"))
    assert (c[0].field, c[0].change) == ("description", "modified")


def test_images_reordered_modified_missing():
    base = make(images=imgs("u1", "u2", "u3"))
    assert diff_content(base, make(images=imgs("u2", "u1", "u3")))[0].change == "reordered"
    assert diff_content(base, make(images=imgs("u1", "u2", "u9")))[0].change == "modified"
    assert diff_content(base, make(images=imgs("u1", "u2")))[0].change == "modified"
    c = diff_content(base, make(images=[]))[0]
    assert (c.field, c.change, c.baseline, c.live) == ("images", "missing", ["u1", "u2", "u3"], [])


def test_aplus_rules():
    assert diff_content(
        make(aplus_available=True, aplus_module_count=3),
        make(aplus_available=True, aplus_module_count=0),
    )[0].change == "missing"
    c = diff_content(
        make(aplus_available=True, aplus_module_count=3),
        make(aplus_available=True, aplus_module_count=2),
    )[0]
    assert (c.field, c.change, c.baseline, c.live) == ("aplus", "modified", 3, 2)
    assert diff_content(
        make(aplus_available=True, aplus_module_count=3),
        make(aplus_available=False, aplus_module_count=None),
    ) == []
    assert diff_content(
        make(aplus_available=True, aplus_module_count=None),
        make(aplus_available=True, aplus_module_count=0),
    ) == []


def test_attribute_change_and_missing():
    base = make(attributes={"color": attr("Rosso"), "material": attr("Cotone")})
    live = make(attributes={"color": attr("Blu")})
    got = by_field(diff_content(base, live))
    assert got["attribute:color"].change == "modified"
    assert got["attribute:color"].baseline == [{"value": "Rosso"}]
    assert got["attribute:color"].live == [{"value": "Blu"}]
    assert got["attribute:material"].change == "missing"


def test_attribute_added_in_live_is_ignored():
    assert diff_content(make(), make(attributes={"color": attr("Blu")})) == []


def test_attribute_other_marketplace_and_tags_ignored():
    base = make(attributes={"color": attr("Rosso") + attr("Red", mp="OTHER")})
    live = make(attributes={"color": [{"value": "Rosso", "language_tag": "en_GB"}]})
    assert diff_content(base, live) == []


def test_volatile_attribute_change_ignored():
    base = make(attributes={"list_price": attr(10)})
    live = make(attributes={"list_price": attr(12)})
    assert diff_content(base, live) == []


def test_covered_attributes_do_not_double_report():
    base = make(title="Old", attributes={"item_name": attr("Old")})
    live = make(title="New", attributes={"item_name": attr("New")})
    assert [c.field for c in diff_content(base, live)] == ["title"]


def test_order_of_changes():
    base = make(
        title="a", bullets=["a"], description="a", images=imgs("u"),
        aplus_available=True, aplus_module_count=1,
        attributes={"zeta": attr("1"), "alpha": attr("1")},
    )
    live = make(
        title="b", bullets=["b"], description="b", images=imgs("v"),
        aplus_available=True, aplus_module_count=2,
        attributes={"zeta": attr("2"), "alpha": attr("2")},
    )
    assert [c.field for c in diff_content(base, live)] == [
        "title", "bullets", "description", "images", "aplus",
        "attribute:alpha", "attribute:zeta",
    ]


# --- families -------------------------------------------------------------

P = "B0TEST0100"


def parent(children, theme="COLOR_NAME"):
    return make(P, child_asins=children, variation_theme=theme)


def child(asin, parents):
    return make(asin, parent_asins=parents)


def test_intact_family_has_no_findings():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001"], parent(["B0TEST0001"]),
        {"B0TEST0001": child("B0TEST0001", [P])},
    )
    assert out == []


def test_child_detached():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001", "B0TEST0002"],
        parent(["B0TEST0001", "B0TEST0002"]),
        {"B0TEST0001": child("B0TEST0001", [P]), "B0TEST0002": child("B0TEST0002", [])},
    )
    assert [(f.kind, f.child_asin, f.parent_asin) for f in out] == [("child_detached", "B0TEST0002", P)]


def test_family_broken_suppresses_child_findings():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001", "B0TEST0002"], parent([]),
        {"B0TEST0001": child("B0TEST0001", []), "B0TEST0002": child("B0TEST0002", [])},
    )
    assert [(f.kind, f.child_asin) for f in out] == [("family_broken", None)]


def test_unfetched_child_is_not_detached():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001"], parent(["B0TEST0001"]), {"B0TEST0001": None}
    )
    assert out == []


def test_unexpected_child():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001"], parent(["B0TEST0001", "B0TEST0009"]),
        {"B0TEST0001": child("B0TEST0001", [P])},
    )
    assert [(f.kind, f.child_asin) for f in out] == [("unexpected_child", "B0TEST0009")]


def test_theme_changed():
    out = diff_family(P, "COLOR_NAME", [], parent([], theme="SIZE_NAME"), {})
    assert [(f.kind, f.baseline, f.live) for f in out] == [("theme_changed", "COLOR_NAME", "SIZE_NAME")]


def test_unfetched_parent_gives_only_child_findings():
    out = diff_family(
        P, "COLOR_NAME", ["B0TEST0001"], None, {"B0TEST0001": child("B0TEST0001", [])}
    )
    assert [f.kind for f in out] == ["child_detached"]
