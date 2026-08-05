"""Typed failures for data-environment authority contracts."""


class DataEnvironmentError(Exception):
    pass


class EnvironmentDefinitionUnavailableError(DataEnvironmentError):
    pass


class RawDataGrantRefusedError(DataEnvironmentError):
    pass


class RecoveryPointUnavailableError(DataEnvironmentError):
    pass
