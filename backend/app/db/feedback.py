"""Privacy-minimal, idempotent beta-feedback persistence."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.db.proposals import connection


FeedbackCategory = Literal["general", "answer_quality", "evidence", "usability", "bug"]


@dataclass(frozen=True)
class FeedbackInput:
    rating: int
    category: FeedbackCategory
    comment: str | None
    client_submission_id: UUID


class FeedbackStorageUnavailable(RuntimeError):
    """Stable public error that never includes database or comment content."""


class FeedbackRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def create(self, user_id: str, submission: FeedbackInput) -> tuple[dict, bool]:
        try:
            async with self.connect() as conn:
                inserted = await (
                    await conn.execute(
                        """insert into beta_feedback
                           (user_id, rating, category, comment, page, client_submission_id)
                           values (%s, %s, %s, %s, %s, %s)
                           on conflict (user_id, client_submission_id) do nothing
                           returning id, rating, category, page, created_at""",
                        (
                            user_id,
                            submission.rating,
                            submission.category,
                            submission.comment,
                            "settings",
                            submission.client_submission_id,
                        ),
                    )
                ).fetchone()
                if inserted:
                    return self._public(inserted), True

                existing = await (
                    await conn.execute(
                        """select id, rating, category, page, created_at
                           from beta_feedback
                           where user_id=%s and client_submission_id=%s""",
                        (user_id, submission.client_submission_id),
                    )
                ).fetchone()
                if not existing:
                    raise RuntimeError("feedback conflict lookup returned no row")
                return self._public(existing), False
        except FeedbackStorageUnavailable:
            raise
        except Exception as exc:
            raise FeedbackStorageUnavailable("피드백을 저장할 수 없습니다.") from exc

    @staticmethod
    def _public(row: dict) -> dict:
        created_at = row["created_at"]
        return {
            "id": str(row["id"]),
            "rating": row["rating"],
            "category": row["category"],
            "page": row["page"],
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
        }
