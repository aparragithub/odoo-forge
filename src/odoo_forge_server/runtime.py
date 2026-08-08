"""Runtime configuration for the optional local operations UI."""

from dataclasses import dataclass
from ipaddress import ip_address

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class UiRuntime:
    """Fail-closed runtime configuration for the optional local UI."""

    bind_host: str
    production: bool = False

    def __post_init__(self) -> None:
        if self.production:
            raise ValueError("read-only UI is forbidden in production")
        try:
            address = ip_address(self.bind_host)
        except ValueError as exc:
            raise ValueError("read-only UI requires a literal loopback bind host") from exc
        if not address.is_loopback:
            raise ValueError("read-only UI requires a loopback bind host")


def guard_loopback_request(request: Request, runtime: UiRuntime) -> None:
    """Reject requests whose socket origin is not the configured literal bind."""
    server = request.scope.get("server")
    if not server or server[0] != runtime.bind_host:
        raise HTTPException(status_code=403, detail="read-only UI is loopback-only")


__all__ = ["UiRuntime", "guard_loopback_request"]
