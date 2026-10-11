"""Publish metadata-only pilot statistics, not unreviewed quality scores."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    baseline = json.loads((ROOT / "artifacts/rag-matrix-reviewed-code/report.json").read_text(encoding="utf-8"))
    pdfium = json.loads((ROOT / "artifacts/rag-matrix-docling-pdfium/report.json").read_text(encoding="utf-8"))
    rows = []
    recipes = []
    for report, parsers, suffix in [(baseline, ["pypdf", "pdfplumber"], ""), (pdfium, ["docling"], " (PDFium)")]:
        if report["manifest_sha256"] != baseline["manifest_sha256"] or report["selected_pages"] != 24:
            raise ValueError("Pilot must use identical corpus and page selections")
        for parser in parsers:
            items = [r for r in report["parsers"] if r["parser"] == parser]
            rows.append({"parser": parser + suffix, "documents_completed": sum(r["status"] == "completed" for r in items),
                "documents_total": len(items), "text_pages": sum(r.get("text_pages", 0) for r in items),
                "text_chars": sum(r.get("text_chars", 0) for r in items), "tables": sum(r.get("tables", 0) for r in items),
                "pictures": sum(r.get("pictures", 0) for r in items),
                "parser_versions": sorted({r["parser_version"] for r in items if r["status"] == "completed"})})
            recipes.extend({**{k: r[k] for k in ("chunking", "search_chunks", "parents", "complete_corpus")},
                            "parser": parser + suffix} for r in report["recipes"] if r["parser"] == parser)
    summary = {"corpus_manifest_sha256": baseline["manifest_sha256"], "documents": 10, "selected_pages": 24,
               "gold_count": 0, "quality_status": "unreviewed_execution_pilot_only", "parsers": rows, "recipes": recipes,
               "native_docling_failure": "KDRI_2025_vol3.pdf: Windows native access violation; retained separately"}
    out = ROOT.parent / "docs/rag_experiments"
    (out / "pilot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 파서·청킹 3×3 실행 파일럿", "", "동일 코퍼스 10개·PDF 24페이지. 최종 품질/최적 구성 판정 전 실행 검증 결과다.", "",
             "| 파서 | 완료 문서 | 텍스트 페이지 | 추출 문자 | 인식 표 블록 | 그림/위치 블록 |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['parser']} | {row['documents_completed']}/{row['documents_total']} | {row['text_pages']} | {row['text_chars']} | {row['tables']} | {row['pictures']} |")
    lines += ["", "| 파서 | 청킹 | 검색 청크 | 부모 문맥 |", "|---|---|---:|---:|"]
    for row in recipes:
        lines.append(f"| {row['parser']} | {row['chunking']} | {row['search_chunks']} | {row['parents']} |")
    lines += ["", "PyPDF의 표/그림 0은 구조 블록을 식별하지 않는 텍스트 기준선이라는 뜻이다.",
              "PDFPlumber 그림 수는 위치 메타데이터 수이며 이미지 이해/OCR 정확도가 아니다.",
              "파서별 표 감지 기준이 다르므로 개수·문자 수가 많다고 정확도가 높다고 판단하지 않는다.",
              "Docling 기본 백엔드는 KDRI 무기질에서 네이티브 오류가 발생했다. PDFium 별도 레시피는 전체 코퍼스에서 검증했다.",
              "", "미완료: 검토된 골드, CER/표 셀·수치 정확도, 스캔 OCR, 검색/Ragas 점수, 임베딩·검색 비교, LangSmith 실험.",
              "실행 로그 시간에는 프로세스 시작·모델 준비가 포함되며, 동시 디버깅도 있어 최종 성능 벤치마크로 사용하지 않는다.",
              "전체 원문 비교/24페이지 사람 검토는 완료되지 않았다. 두 페이지의 원본 렌더링만 대조했다.",
              "", "[전체 계획 및 판본·충돌 정책](PLAN.md)", ""]
    (out / "PILOT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(out / "PILOT_REPORT.md")


if __name__ == "__main__":
    main()
