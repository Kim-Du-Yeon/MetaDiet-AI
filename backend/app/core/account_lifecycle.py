"""Shared account lifecycle identifiers and guards."""
import hashlib


class AccountDeletionInProgress(PermissionError):
    pass


def auth_id_hash(auth_id: str) -> str:
    return hashlib.sha256(str(auth_id).encode("utf-8")).hexdigest()
