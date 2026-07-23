"""Pure, provider-neutral identity domain types — zero I/O.

Mirrors `pipeline/types.py`: plain pydantic `BaseModel`s carrying only
role-mapping-relevant identity vocabulary, no IdP-vendor or protocol-handshake
vocabulary. A (future, out of scope) adapter maps these neutral values onto a
concrete identity provider.
"""

from __future__ import annotations

from pydantic import BaseModel


class AuthenticationRequest(BaseModel):
    audience: str
    context: dict[str, str] = {}


class AuthenticationChallenge(BaseModel):
    challenge_id: str
    payload: str


class IdentityAssertion(BaseModel):
    challenge_id: str
    value: str


class SessionRef(BaseModel):
    reference: str


class AuthenticatedPrincipal(BaseModel):
    subject: str
    claims: dict[str, str] = {}
    session: SessionRef


__all__ = [
    "AuthenticationRequest",
    "AuthenticationChallenge",
    "IdentityAssertion",
    "SessionRef",
    "AuthenticatedPrincipal",
]
