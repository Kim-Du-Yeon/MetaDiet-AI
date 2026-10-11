"""Transactional application-data deletion followed by retryable Auth deletion."""
import asyncio

from app.core.account_lifecycle import auth_id_hash
from app.db.proposals import connection
from app.db.supabase_client import get_supabase


class AccountDeletionPartialFailure(RuntimeError):
    def __init__(self):
        super().__init__("auth_identity_deletion_failed")
        self.application_data_deleted = True


class InvalidAuthSession(PermissionError):
    pass


async def _delete_auth_identity(auth_id: str) -> None:
    await asyncio.to_thread(get_supabase().auth.admin.delete_user, auth_id)


class AccountDeletionService:
    def __init__(self, *, connect=connection, delete_auth=_delete_auth_identity):
        self.connect = connect
        self.delete_auth = delete_auth

    async def delete(self, auth_id: str, session_id: str) -> dict:
        """Delete app data atomically, then remove the external Auth identity.

        If Auth is unavailable after the DB commit, a retry remains possible
        because the endpoint authenticates by JWT subject rather than users.id.
        """
        application_data_deleted = False
        hashed_auth_id = auth_id_hash(auth_id)
        async with self.connect() as conn:
            await conn.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"account-lifecycle:{hashed_auth_id}",),
            )
            active_session = await (
                await conn.execute(
                    "select 1 from auth.sessions where id=%s and user_id=%s",
                    (session_id, auth_id),
                )
            ).fetchone()
            if not active_session:
                raise InvalidAuthSession("auth_session_not_active")
            await conn.execute(
                "insert into account_deletion_tombstones(auth_id_hash) values(%s) "
                "on conflict(auth_id_hash) do nothing",
                (hashed_auth_id,),
            )
            cursor = await conn.execute(
                "select id from users where auth_id=%s for update", (auth_id,)
            )
            row = await cursor.fetchone()
            if row:
                user_id = str(row["id"])
                # Wait for all active conversations to finish and prevent new
                # ones from entering until the user row and checkpoints vanish.
                await conn.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"account:{user_id}",),
                )
                thread_pattern = f"{user_id}\\_%"
                # Checkpoint tables have no users FK. Children are deleted first.
                await conn.execute(
                    "delete from checkpoint_writes where thread_id like %s escape '\\'",
                    (thread_pattern,),
                )
                await conn.execute(
                    "delete from checkpoint_blobs where thread_id like %s escape '\\'",
                    (thread_pattern,),
                )
                await conn.execute(
                    "delete from checkpoints where thread_id like %s escape '\\'",
                    (thread_pattern,),
                )
                # Domain tables, proposals and budgets have ON DELETE CASCADE.
                await conn.execute("delete from users where id=%s", (user_id,))
            application_data_deleted = True

        try:
            await self.delete_auth(auth_id)
        except Exception:
            if application_data_deleted:
                raise AccountDeletionPartialFailure() from None
            raise
        cleanup_pending = False
        try:
            async with self.connect() as conn:
                await conn.execute(
                    "delete from account_deletion_tombstones where auth_id_hash=%s",
                    (hashed_auth_id,),
                )
        except Exception:
            # Auth is already gone; retaining the hashed tombstone fails closed
            # and can be cleaned by an operator without restoring user data.
            cleanup_pending = True
        return {"status": "deleted", "tombstone_cleanup_pending": cleanup_pending}
