"""Marketplace-specific health evidence from the Listings Items response for a SKU."""
from datetime import datetime


def listing_health_observation(
    payload: dict | None, marketplace_id: str, asin: str, sku: str | None, account_type: str,
) -> dict:
    # Listings Items documents BUYABLE only for seller listings. A vendor's
    # DISCOVERABLE-only summary is not evidence that shoppers cannot buy it.
    health = {"statuses": None, "issues": None, "buyability_applicable": account_type == "seller"}
    if not payload or (payload.get("sku") and payload["sku"] != sku):
        return health
    summary = next((s for s in payload.get("summaries") or []
                    if isinstance(s, dict) and s.get("marketplaceId") == marketplace_id), {})
    if summary.get("asin") and summary["asin"] != asin:
        return health
    flags = summary.get("status")
    if isinstance(flags, list) and all(isinstance(flag, str) for flag in flags):
        health["statuses"] = flags
    if isinstance(payload.get("issues"), list):
        issues = []
        for issue in payload["issues"]:
            if not isinstance(issue, dict):
                return health
            if issue.get("marketplaceIds") and marketplace_id not in issue["marketplaceIds"]:
                continue
            enforcement = issue.get("enforcements") or {}
            issues.append({
                "code": issue.get("code"), "severity": issue.get("severity"),
                "message": issue.get("message"),
                "attributes": issue.get("attributeNames") or [],
                "actions": [a["action"] for a in enforcement.get("actions") or [] if a.get("action")],
                "exemption": (enforcement.get("exemption") or {}).get("status"),
            })
        health["issues"] = issues
    return health


def listing_health_snapshot(observed: dict, checked_at: datetime, previous: dict | None) -> dict:
    """Preserve each last known field and its actual observation time after a partial read."""
    now = checked_at.isoformat()
    health = {"checked_at": now, "buyability_applicable": observed["buyability_applicable"]}
    for key in ("statuses", "issues"):
        stamp = f"{key}_observed_at"
        health[f"{key}_read"] = observed[key] is not None
        if observed[key] is not None:
            health[key], health[stamp] = observed[key], now
        else:
            health[key] = (previous or {}).get(key)
            health[stamp] = (previous or {}).get(stamp)
    return health


def health_needs_attention(health: dict | None) -> bool:
    if not health:
        return False
    if health["statuses_read"] and (
        (health["buyability_applicable"] and "BUYABLE" not in health["statuses"])
        or "DISCOVERABLE" not in health["statuses"]
    ):
        return True
    return health["issues_read"] and bool(health["issues"])
