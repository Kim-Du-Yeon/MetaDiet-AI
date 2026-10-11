"""Deterministic edition and conflict policy for reviewed, normalized claims.

Raw retrieval passages are not normalized claims: extraction must retain evidence
and be reviewed before this module may authorize a numeric target policy.
"""
from collections import defaultdict
import math

POLICY_VERSION = "evidence-v1"
AUTHORITY = {"national_guideline": 3, "international_guideline": 3,
             "society_guideline": 2, "systematic_review": 1, "single_study": 0}


def select_editions(sources: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for source in sources:
        if source.get("status") in {"withdrawn", "draft", "superseded"}:
            continue
        # Unknown families are never silently grouped together.
        key = (source.get("family") or source["id"], source["population"], source.get("conditions", ""))
        groups[key].append(source)
    selected = []
    for group in groups.values():
        newest = max((s["year"], s.get("revision_date", "")) for s in group)
        selected.extend(s for s in group if (s["year"], s.get("revision_date", "")) == newest)
    return selected


def resolve_claims(claims: list[dict], *, region: str, population: str, conditions: str = "") -> list[dict]:
    """Do not compare differing units/conditions, average conflicts or use recency
    across unrelated authorities as a tie-breaker. A tie requires review.
    """
    applicable = [c for c in claims if c["population"] == population and c.get("conditions", "") == conditions]
    for claim in applicable:
        if claim["authority"] not in AUTHORITY or not math.isfinite(claim["low"]) or not math.isfinite(claim["high"]) or claim["low"] > claim["high"]:
            raise ValueError("Invalid reviewed claim")
    grouped = defaultdict(list)
    for claim in select_editions(applicable):
        grouped[claim["claim_key"]].append(claim)
    results = []
    for key, group in grouped.items():
        base = {"claim_key": key, "policy_version": POLICY_VERSION, "selected": None,
                "considered_ids": [c["id"] for c in group], "conflicting_ids": []}
        if len({c["unit"] for c in group}) > 1:
            results.append({**base, "status": "incomparable", "reason": "Different units require an explicitly validated conversion"})
            continue
        def priority(claim):
            regional_guideline = claim["region"] == region and claim["authority"] in {"national_guideline", "international_guideline"}
            return (int(regional_guideline), AUTHORITY[claim["authority"]])
        maximum = max(priority(c) for c in group)
        leaders = [c for c in group if priority(c) == maximum]
        # Distinct ranges represent differing recommendations even if overlapping;
        # do not silently intersect or average them into a new recommendation.
        if len({(c["low"], c["high"]) for c in leaders}) > 1:
            results.append({**base, "status": "unresolved", "conflicting_ids": [c["id"] for c in leaders],
                            "reason": "Equal-priority applicable guidance disagrees; strategy blocked pending review"})
            continue
        selected = leaders[0]
        conflicts = [c["id"] for c in group if (c["low"], c["high"]) != (selected["low"], selected["high"])]
        results.append({**base, "selected": selected, "conflicting_ids": conflicts,
            "status": "resolved_with_disclosure" if conflicts else "consistent",
            "reason": "Applicable regional guidance, then authority; latest edition within each family"})
    return results
