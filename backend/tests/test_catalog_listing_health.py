from datetime import datetime, timedelta, timezone

from app.services.catalog_monitor.listing_health import (
    health_needs_attention, listing_health_observation, listing_health_snapshot,
)


def test_marketplace_filtered_issues_and_vendor_visibility():
    payload = {
        "sku": "SKU",
        "summaries": [{"asin": "ASIN", "marketplaceId": "IT", "status": ["DISCOVERABLE"]}],
        "issues": [
            {"marketplaceIds": ["DE"], "code": "other-market"},
            {"marketplaceIds": ["IT"], "code": "90220", "attributeNames": ["material"],
             "enforcements": {"actions": [{"action": "ATTRIBUTE_SUPPRESSED"}], "exemption": {"status": "EXEMPT"}}},
        ],
    }
    observed = listing_health_observation(payload, "IT", "ASIN", "SKU", "vendor")
    assert not observed["buyability_applicable"]
    assert observed["statuses"] == ["DISCOVERABLE"]
    assert [(i["code"], i["actions"], i["exemption"]) for i in observed["issues"]] == [
        ("90220", ["ATTRIBUTE_SUPPRESSED"], "EXEMPT"),
    ]
    now = datetime.now(timezone.utc)
    assert health_needs_attention(listing_health_snapshot(observed, now, None))
    payload["issues"] = []
    for account_type, needs_attention in [("vendor", False), ("seller", True)]:
        fresh = listing_health_observation(payload, "IT", "ASIN", "SKU", account_type)
        assert health_needs_attention(listing_health_snapshot(fresh, now, None)) is needs_attention
    assert listing_health_observation(payload, "IT", "BAD", "SKU", "vendor")["issues"] is None


def test_health_keeps_previous_field_observation_dates_and_distinguishes_absence():
    now = datetime.now(timezone.utc)
    fields = {"statuses": [], "issues": [], "buyability_applicable": True}
    first = listing_health_snapshot(fields, now, None)
    assert health_needs_attention(first)
    observed = listing_health_observation({"sku": "s"}, "IT", "a", "s", "seller")
    failed = listing_health_snapshot(observed, now + timedelta(days=1), first)
    assert failed["statuses_observed_at"] == failed["issues_observed_at"] == first["checked_at"]
    assert failed["checked_at"] != failed["statuses_observed_at"]
    assert not health_needs_attention(failed)
    without_history = listing_health_snapshot(observed, now, None)
    assert without_history["statuses"] is without_history["issues"] is None
    assert not health_needs_attention(without_history)
