"""Errors raised by the catalog-index adapter."""


class CatalogSourceError(Exception):
    """Raised when the declarative catalog source cannot be read or parsed."""


__all__ = ["CatalogSourceError"]
