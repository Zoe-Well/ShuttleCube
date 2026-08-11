import hashlib
import secrets
from dataclasses import dataclass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SessionTokens:
    session: str
    csrf: str


def issue_tokens() -> SessionTokens:
    return SessionTokens(session=new_token(), csrf=new_token())
