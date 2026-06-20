from app.rag.region_guidance import get_region_guidance, REGION_GUIDANCE


def test_kr_returns_kdris_priority_text():
    assert get_region_guidance("KR") == REGION_GUIDANCE["KR"]
    assert "KDRIs" in get_region_guidance("KR")


def test_intl_returns_who_priority_text():
    assert get_region_guidance("INTL") == REGION_GUIDANCE["INTL"]
    assert "WHO" in get_region_guidance("INTL")


def test_missing_or_unknown_region_defaults_to_kr():
    assert get_region_guidance(None) == REGION_GUIDANCE["KR"]
    assert get_region_guidance("") == REGION_GUIDANCE["KR"]
    assert get_region_guidance("JP") == REGION_GUIDANCE["KR"]
