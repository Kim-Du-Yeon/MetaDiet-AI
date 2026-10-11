import pytest


def test_latest_applies_only_to_same_guideline_family_and_population():
    from app.rag.evidence_policy import select_editions
    sources = [dict(id="old", family="KDRI-energy", population="adult", year=2020),
               dict(id="new", family="KDRI-energy", population="adult", year=2025),
               dict(id="child", family="KDRI-energy", population="child", year=2026),
               dict(id="who", family="WHO-fat", population="adult", year=2023)]
    assert {s["id"] for s in select_editions(sources)} == {"new", "child", "who"}


def test_errata_revision_wins_within_same_year():
    from app.rag.evidence_policy import select_editions
    source = dict(id="first", family="KDRI", population="adult", year=2025, revision_date="2026-02-02")
    assert select_editions([source, {**source, "id": "corrected", "revision_date": "2026-03-16"}])[0]["id"] == "corrected"


def test_regional_single_study_does_not_override_official_guideline():
    from app.rag.evidence_policy import resolve_claims
    base = dict(id="official", claim_key="fat", source="WHO", authority="international_guideline", region="INTL",
        family="WHO-fat", population="adult", year=2023, unit="percent_energy", low=15, high=30)
    other = {**base, "id": "study", "region": "KR", "authority": "single_study", "family": "study", "year": 2026, "low": 50, "high": 60}
    assert resolve_claims([base, other], region="KR", population="adult")[0]["selected"]["id"] == "official"


def test_conflicting_kr_and_who_ranges_choose_applicable_kr_and_disclose_conflict():
    from app.rag.evidence_policy import resolve_claims
    kr = dict(id="kr", claim_key="carb_ratio", source="KDRI", authority="national_guideline", region="KR",
        family="KDRI-energy", population="adult", year=2025, unit="percent_energy", low=50, high=65)
    who = {**kr, "id": "who", "source": "WHO", "region": "INTL", "family": "WHO-carbs", "low": 40, "high": 49}
    result = resolve_claims([who, kr], region="KR", population="adult")
    assert result[0]["status"] == "resolved_with_disclosure"
    assert result[0]["selected"]["id"] == "kr"
    assert result[0]["conflicting_ids"] == ["who"]


def test_equal_priority_disagreement_blocks_numeric_strategy():
    from app.rag.evidence_policy import resolve_claims
    claim = dict(id="a", claim_key="protein", source="one", authority="society_guideline", region="INTL",
        family="a", population="healthy_exercising_adult", year=2025, unit="g_per_kg", low=1.2, high=1.4)
    result = resolve_claims([claim, {**claim, "id": "b", "family": "b", "low": 1.6, "high": 2.0}],
                            region="INTL", population="healthy_exercising_adult")
    assert result[0]["status"] == "unresolved"
    assert result[0]["selected"] is None


def test_incomparable_units_are_not_averaged():
    from app.rag.evidence_policy import resolve_claims
    base = dict(id="a", claim_key="protein", source="one", authority="society_guideline", region="INTL",
        family="a", population="adult", year=2025, unit="g_per_kg", low=1.2, high=1.4)
    result = resolve_claims([base, {**base, "id": "b", "unit": "g_per_day"}], region="KR", population="adult")
    assert result[0]["status"] == "incomparable"
    assert result[0]["selected"] is None
