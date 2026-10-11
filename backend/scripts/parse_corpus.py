"""Parse local corpus manifest entries without modifying Pinecone or BM25."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.ingestion import SourceDocument, parse_document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, help="JSON array with SourceDocument fields")
    parser.add_argument("--parser", choices=["pypdf", "docling", "pdfplumber"], default="pypdf")
    parser.add_argument("--pages", type=int, nargs="+")
    parser.add_argument("--ocr", action="store_true", help="Docling + installed Tesseract kor/eng only")
    parser.add_argument("--docling-backend", choices=["docling_parse", "pdfium"], default="docling_parse")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ingestion"))
    args = parser.parse_args()
    for row in json.loads(args.manifest.read_text(encoding="utf-8")):
        row["path"] = args.manifest.parent / row["path"]
        destination = parse_document(SourceDocument(**row), args.output, parser=args.parser, pages=args.pages, ocr=args.ocr, docling_backend=args.docling_backend)
        print(destination)


if __name__ == "__main__":
    main()
