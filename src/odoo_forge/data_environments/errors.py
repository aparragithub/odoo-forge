"""Typed failures for data-environment authority contracts."""


class DataEnvironmentError(Exception):
    """Base error for data-environment contract failures."""


class EnvironmentDefinitionUnavailableError(DataEnvironmentError):
    """Raised when a canonical environment definition is unavailable."""


class RawDataGrantRefusedError(DataEnvironmentError):
    """Raised when raw-data delivery lacks an accepted grant."""


class RecoveryPointUnavailableError(DataEnvironmentError):
    """Raised when an existing target lacks a usable recovery point."""
