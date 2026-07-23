import ast
import inspect

from odoo_forge import pipeline
from odoo_forge.pipeline import types as pipeline_types
from odoo_forge.ports import pipeline_provider
from odoo_forge.ports.pipeline_provider import PipelineProvider

_DENYLIST = (
    "github",
    "gitlab",
    "jenkins",
    "circleci",
    "travis",
    "azure",
    "buildkite",
    "teamcity",
    "argo",
    "tekton",
    "drone",
    "actions",
    "workflow",
    "runner",
    "yaml",
)


class _FakePipelineProvider:
    """Structural stand-in — not a real adapter, just satisfies the shape.

    Uses plain `object`-typed parameters rather than the real
    `PipelineRunSpec`/`PipelineRunRef`/`PipelineRunStatus` types, proving the
    port contract is satisfiable by `isinstance` without needing the real
    domain types (`runtime_checkable` verifies method NAMES only).
    """

    def trigger(self, spec: object) -> object:
        return "run-ref"

    def status(self, ref: object) -> object:
        return "run-status"

    def logs(self, ref: object) -> str:
        return "log text"


def test_conforming_class_satisfies_pipeline_provider_protocol() -> None:
    provider = _FakePipelineProvider()

    assert isinstance(provider, PipelineProvider)


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _MissingLogs:
        """Conforms to every method except `logs` — must fail `isinstance`."""

        def trigger(self, spec: object) -> object:
            return "run-ref"

        def status(self, ref: object) -> object:
            return "run-status"

    assert not isinstance(_MissingLogs(), PipelineProvider)


def test_trigger_status_logs_happy_path_returns_neutral_shapes() -> None:
    from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec, PipelineRunStatus

    class _NeutralProvider:
        def trigger(self, spec: PipelineRunSpec) -> PipelineRunRef:
            return PipelineRunRef(run_id="run-1")

        def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
            return PipelineRunStatus(state="succeeded")

        def logs(self, ref: PipelineRunRef) -> str:
            return "output text"

    provider: PipelineProvider = _NeutralProvider()
    spec = PipelineRunSpec(definition="build-and-test")

    ref = provider.trigger(spec)
    status = provider.status(ref)
    output = provider.logs(ref)

    assert isinstance(ref, PipelineRunRef)
    assert ref.run_id == "run-1"
    assert isinstance(status, PipelineRunStatus)
    assert status.state == "succeeded"
    assert output == "output text"


def test_status_query_for_unknown_run_may_raise() -> None:
    from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunStatus

    class _UnknownRunProvider:
        def trigger(self, spec: object) -> PipelineRunRef:
            return PipelineRunRef(run_id="run-1")

        def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
            if ref.run_id != "run-1":
                raise KeyError(ref.run_id)
            return PipelineRunStatus(state="succeeded")

        def logs(self, ref: PipelineRunRef) -> str:
            return ""

    provider: PipelineProvider = _UnknownRunProvider()

    try:
        provider.status(PipelineRunRef(run_id="unknown-run"))
    except KeyError:
        pass
    else:
        raise AssertionError("expected a distinct signal for an unrecognized run reference")


def test_pipeline_port_documents_neutral_verbs() -> None:
    trigger_doc = PipelineProvider.trigger.__doc__
    status_doc = PipelineProvider.status.__doc__
    logs_doc = PipelineProvider.logs.__doc__

    assert trigger_doc is not None
    assert "run" in trigger_doc.lower()
    assert status_doc is not None
    assert "status" in status_doc.lower() or "state" in status_doc.lower()
    assert logs_doc is not None
    assert "output" in logs_doc.lower() or "log" in logs_doc.lower()


def test_ci_engine_denylist_absent_from_public_surface() -> None:
    port_source = inspect.getsource(pipeline_provider).lower()
    types_source = inspect.getsource(pipeline_types).lower()

    for token in _DENYLIST:
        assert token not in port_source, f"denylisted token {token!r} found in pipeline_provider.py"
        assert token not in types_source, f"denylisted token {token!r} found in pipeline/types.py"


def test_no_adapter_import_in_pipeline_provider() -> None:
    tree = ast.parse(inspect.getsource(pipeline_provider))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_fragments = ("adapter", "subprocess", "requests", "httpx")
    for fragment in forbidden_fragments:
        assert not any(fragment in module.lower() for module in imported_modules)

    assert pipeline.__name__ == "odoo_forge.pipeline"
