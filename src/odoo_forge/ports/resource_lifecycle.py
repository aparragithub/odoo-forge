from typing import Protocol, runtime_checkable

from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    OperationIdentity,
)
from odoo_forge.resource_lifecycle.types import (
    DatabaseObservation,
    ExpirationDecision,
    LifecycleJournalEvent,
    LifecycleResource,
)
from odoo_forge.tenancy.types import ProjectScope


@runtime_checkable
class DatabaseLifecycleGateway(Protocol):
    """Provider-only observation and recovery boundary.

    Registry reads remain a separate `InstanceRegistry` dependency of the service.
    """

    def observe(self, scope: ProjectScope) -> tuple[DatabaseObservation, ...]: ...

    def quarantine(self, ref: DatabaseRef) -> DatabaseRef: ...

    def adopt(self, ref: DatabaseRef) -> DatabaseRef: ...

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation: ...

    def delete(self, creation: DatabaseCreation) -> None: ...

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport: ...


@runtime_checkable
class LifecycleJournal(Protocol):
    """Append and read immutable lifecycle audit snapshots."""

    def append(self, event: LifecycleJournalEvent) -> LifecycleJournalEvent: ...

    def events(self) -> tuple[LifecycleJournalEvent, ...]: ...


@runtime_checkable
class LifecycleAlertSink(Protocol):
    """Publish lifecycle alerts without authorizing mutations."""

    def alert(self, resource: LifecycleResource, decision: ExpirationDecision) -> None: ...


@runtime_checkable
class LifecycleSchedulerGate(Protocol):
    """Expose the explicit opt-in gate for automated lifecycle runs."""

    def enabled(self) -> bool: ...
