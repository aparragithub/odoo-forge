"""Pure domain error family for image-registry operations."""


class RegistryError(Exception):
    """Base class for image-registry failures."""


class UnsupportedRegistryError(RegistryError):
    def __init__(self, registry: str, *, supported: str = "ghcr.io") -> None:
        self.registry = registry
        self.supported = supported
        super().__init__(
            f"unsupported registry '{registry}' — only '{supported}' is supported in this slice"
        )


class MalformedImageReferenceError(RegistryError):
    def __init__(self, ref: str, detail: str) -> None:
        self.ref = ref
        self.detail = detail
        super().__init__(f"malformed image reference '{ref}': {detail}")


class RegistryAuthenticationError(RegistryError):
    def __init__(self, ref: str) -> None:
        self.ref = ref
        super().__init__(f"GHCR authentication failed for '{ref}'")


class RegistryImageNotFoundError(RegistryError):
    def __init__(self, ref: str) -> None:
        self.ref = ref
        super().__init__(f"image reference not found in registry: '{ref}'")


class RegistryUnavailableError(RegistryError):
    def __init__(self, ref: str, detail: str) -> None:
        self.ref = ref
        self.detail = detail
        super().__init__(f"cannot reach registry for '{ref}': {detail}")


__all__ = [
    "RegistryError",
    "UnsupportedRegistryError",
    "MalformedImageReferenceError",
    "RegistryAuthenticationError",
    "RegistryImageNotFoundError",
    "RegistryUnavailableError",
]
