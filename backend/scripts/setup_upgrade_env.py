"""Append missing upgrade settings without reading secrets into terminal output."""
from pathlib import Path
import re


DEFAULTS = {
    "GEMINI_API_KEY": "", "LANGSMITH_API_KEY": "",
    "GEMINI_MODEL": "gemini-3.8-flash",
    "GEMINI_VISION_MODEL": "gemini-3.8-flash",
    "GEMINI_EVAL_MODEL": "gemini-3.8-flash",
    "EMBEDDING_MODEL": "gemini-embedding-2",
    "EMBEDDING_DIMENSION": "3072",
    "PINECONE_NAMESPACE": "metadiet-gemini-v1",
    "LANGSMITH_TRACING": "true",
    "LANGSMITH_ENDPOINT": "https://api.smith.langchain.com",
    "LANGSMITH_PROJECT": "metadiet-gemini-dev",
    "MODEL_TIMEOUT_SECONDS": "30", "MODEL_MAX_RETRIES": "0",
    "AGENT_MAX_MODEL_CALLS": "12", "AGENT_MAX_TOOL_CALLS": "20",
    "AGENT_MAX_REPLANS": "2", "AGENT_MAX_VALIDATION_ATTEMPTS": "3",
    "AGENT_TIMEOUT_SECONDS": "120",
}


def append_missing(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    existing = set(re.findall(r"^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=", content, re.M))
    missing = {key: value for key, value in DEFAULTS.items() if key not in existing}
    if missing:
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n# Gemini agent upgrade (existing values preserved)\n")
            stream.writelines(f"{key}={value}\n" for key, value in missing.items())
    return list(missing)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for name in (".env", ".env.example"):
        added = append_missing(root / name)
        print(f"{name}: added {len(added)} missing settings; existing values preserved")
