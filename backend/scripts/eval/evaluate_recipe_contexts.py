"""Pilot Ragas on exact budgeted contexts from the parser/chunking comparator."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "artifacts/ragas-runtime"))
from app.core.config import get_settings
from app.core.llm import get_evaluation_model
from app.core.embeddings import GeminiEmbeddings
from app.rag.qa import answer_from_knowledge, QA_PROMPT
from app.rag.region_guidance import get_region_guidance
from langchain_core.documents import Document
from langsmith import Client, tracing_context
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import faithfulness, context_recall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig


async def generate(rows, recipe):
    semaphore = asyncio.Semaphore(4)
    async def one(row):
        async with semaphore:
            texts = row["retrieved_contexts"]
            documents = [Document(page_content=text, metadata={**meta, "page": ",".join(map(str, meta["pdf_pages"]))})
                         for text, meta in zip(texts, row["context_metadata"], strict=True)]
            context = "\n\n".join(f"[출처: {d.metadata['source_file']}, p.{d.metadata['page']}]\n{d.page_content}" for d in documents)
            answer = await answer_from_knowledge(row["question"], user_region="INTL", retrieval_result={
                "docs": documents, "context": context, "grounded": bool(texts), "max_score": 0},
                config={"metadata": {"recipe": recipe, "case_id": row["id"], "scope": "rag-pilot"}})
            return {**row, "response": answer["answer"], "actual_prompt_context": context,
                    "generation_token_usage": answer.get("token_usage")}
    return await asyncio.gather(*(one(row) for row in rows))


def mean(values):
    valid = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return sum(valid) / len(valid) if valid else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--recipe", help="Run one recipe stem in a fresh process; never merge retries silently")
    parser.add_argument("--report-name", default="ragas-pilot-report.json")
    args = parser.parse_args()
    settings = get_settings()
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    report = {"scope": "two-source, 20-query pilot; not final recipe selection", "generation_model": settings.gemini_model,
              "judge_model": settings.gemini_eval_model, "embedding_model": settings.embedding_model, "recipes": []}
    report["evaluation_id"] = uuid4().hex
    if Path(args.report_name).name != args.report_name:
        parser.error("report-name must be a filename")
    output = args.directory / args.report_name
    paths = sorted(args.directory.glob("*-contexts.json"))
    if args.recipe:
        paths = [path for path in paths if path.stem == args.recipe]
        if not paths:
            parser.error("Unknown recipe stem")
    with tracing_context(client=client, project_name=settings.langsmith_project, enabled=settings.langsmith_tracing.lower() == "true"):
        for path in paths:
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                identity = hashlib.sha256(path.read_bytes() + settings.gemini_model.encode()
                    + str(QA_PROMPT).encode() + get_region_guidance("INTL").encode()).hexdigest()[:16]
                generated = path.with_name(f"{path.stem}-answers-{identity}.json")
                if generated.exists():
                    rows = json.loads(generated.read_text(encoding="utf-8"))
                else:
                    rows = asyncio.run(generate(rows, path.stem))
                    generated.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                samples = [SingleTurnSample(user_input=r["question"], retrieved_contexts=[r["actual_prompt_context"]] if r["actual_prompt_context"] else [],
                           response=r["response"], reference=r["gold_answer"]) for r in rows]
                results = evaluate(EvaluationDataset(samples=samples), metrics=[faithfulness, context_recall],
                    llm=LangchainLLMWrapper(get_evaluation_model()), embeddings=LangchainEmbeddingsWrapper(GeminiEmbeddings()),
                    raise_exceptions=True, run_config=RunConfig(max_workers=4, max_retries=0, timeout=120))
                frame = results.to_pandas()
                scores_path = path.with_name(f"{path.stem}-ragas-{report['evaluation_id']}.json")
                frame.to_json(scores_path, orient="records", force_ascii=False)
                report["recipes"].append({"recipe": path.stem, "status": "completed", "n": len(rows),
                    "faithfulness": mean(frame["faithfulness"].tolist()), "context_recall": mean(frame["context_recall"].tolist()),
                    "coverage": {metric: {"valid": sum(isinstance(v, (int, float)) and math.isfinite(v) for v in frame[metric].tolist()),
                        "total": len(frame)} for metric in ("faithfulness", "context_recall")}, "scores": str(scores_path),
                    "abstained": sum(r["response"] == "제공된 자료에서 근거를 찾지 못했습니다." for r in rows), "answers": str(generated)})
            except Exception as exc:
                # Never log provider response bodies: they may contain prompt data.
                code = getattr(exc, "code", None)
                report["recipes"].append({"recipe": path.stem, "status": "failed", "error_type": type(exc).__name__,
                    "http_status": code if isinstance(code, int) else None})
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(path.stem, report["recipes"][-1]["status"], flush=True)
    client.flush()


if __name__ == "__main__":
    main()
