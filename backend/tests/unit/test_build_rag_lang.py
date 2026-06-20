from scripts.build_rag import _detect_lang


def test_filename_override_applies_for_mistagged_korean_doc():
    assert _detect_lang("guideline2022_vol8.pdf") == "ko"


def test_korean_filename_without_override_detected_by_hangul():
    assert _detect_lang("01+2020+한국인+영양소+섭취기준+-+에너지와+다량영양소.pdf") == "ko"


def test_english_filename_without_override_detected_as_en():
    assert _detect_lang("WHO_TRS_894.pdf") == "en"
