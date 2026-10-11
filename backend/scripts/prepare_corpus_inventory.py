"""Verify downloaded PDFs and prepare the explicitly selected ten-document corpus."""
import hashlib
import json
import shutil
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = ROOT / "backend/artifacts/corpus-downloads"
DEST = ROOT / "docs/nutrition"
KNS = "https://kns.or.kr/fileroom/fileroom_view.asp?BoardID=Kdr&idx=167"


def main():
    sources = []
    inventory = []
    for number, title in [(1, "에너지와 다량영양소"), (2, "비타민"), (3, "무기질")]:
        matches = list((DOWNLOADS / "kdri2025").rglob(f"*2025 KDRI-{number}권*.pdf"))
        if len(matches) != 1:
            raise ValueError(f"Expected one KDRI volume {number}")
        filename = f"KDRI_2025_vol{number}.pdf"
        sources.append((matches[0], filename, f"2025 한국인 영양소 섭취기준: {title}", KNS, "ko",
                        "2025; errata applied through 2026-03-16, official f4 archive",
                        "General population; select adult, non-pregnant/non-lactating rows for this service",
                        "MOHW/KNS official public edition; attribute source; confirm embedded KOGL terms before redistribution/commercial deployment"))
    who = [("carbohydrate", "2023", "9789240073593"), ("total_fat", "2023", "9789240073654"),
           ("saturated_trans_fat", "2023", "9789240073630"), ("sugars", "2015", "9789241549028"),
           ("sodium", "2012", "9789241504836")]
    for topic, year, isbn in who:
        filename = f"WHO_{topic}_{year}.pdf"
        sources.append((DOWNLOADS / filename, filename, f"WHO guideline: {topic.replace('_', ' ')}",
                        f"https://www.who.int/publications/i/item/{isbn}", "en", year,
                        "Adults and children; use adult recommendations with exclusions/remarks preserved",
                        "WHO official PDF; preserve attribution. Check document licence: 2023 CC BY-NC-SA 3.0 IGO requires permission for commercial use; older editions have their own terms"))
    sources.extend([
        (DEST / "guideline2022_vol8.pdf", "guideline2022_vol8.pdf", "대한비만학회 비만 진료지침 2022 요약본",
         "https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf", "ko", "2022",
         "Clinical obesity guideline; lifestyle evidence only, no individual medical prescription",
         "Existing baseline file; public source recorded, licence/latest edition needs review before production activation"),
        (DEST / "s12970-017-0177-8.pdf", "s12970-017-0177-8.pdf", "ISSN position stand: protein and exercise",
         "https://doi.org/10.1186/s12970-017-0177-8", "en", "2017",
         "Healthy exercising individuals; do not generalize athlete-specific doses to all users",
         "Existing open-access article; retain attribution and verify article licence")])
    for origin, filename, title, url, lang, edition, population, notes in sources:
        data = origin.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError(f"Not a PDF: {filename}")
        reader = PdfReader(origin)
        if not reader.pages:
            raise ValueError(f"Empty PDF: {filename}")
        target = DEST / filename
        if origin.resolve() != target.resolve():
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"Refusing to overwrite a different edition: {filename}")
            shutil.copyfile(origin, target)
        sources_row = dict(path=filename, title=title, source_url=url, language=lang,
                           edition=edition, population=population, usage_notes=notes)
        inventory.append({**sources_row, "sha256": hashlib.sha256(data).hexdigest(), "pdf_pages": len(reader.pages),
                          "status": "experiment_selected_not_production_activated", "quality_review_status": "unreviewed"})
    sources = [{k: row[k] for k in ("path", "title", "source_url", "language", "edition", "population", "usage_notes")} for row in inventory]
    (DEST / "corpus_manifest.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DEST / "corpus_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(sources)} selected PDFs: 4 Korean / 6 English; {len(list(DEST.glob('*.pdf')))} PDFs preserved in folder")


if __name__ == "__main__":
    main()
