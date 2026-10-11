"""CORS origin configuration shared by local and hosted deployments."""
import os


LOCAL_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]


def allowed_origins(configured: str | None = None) -> list[str]:
    """Return local origins plus an explicit comma-separated deployment allowlist."""
    raw = os.getenv("CORS_ORIGINS", "") if configured is None else configured
    result = list(LOCAL_ORIGINS)
    for origin in raw.split(","):
        normalized = origin.strip().rstrip("/")
        if normalized and normalized not in result:
            result.append(normalized)
    return result
