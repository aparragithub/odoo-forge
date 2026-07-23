from odoo_forge_pipeline_github.transport import GitHubActionsTransport


class _FakeTransportForProtocolCheck:
    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
        return None

    def latest_run_id(self, workflow: str, ref: str) -> str:
        return "1"

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        return ("queued", None)

    def get_run_logs(self, run_id: str) -> str:
        return ""


def test_transport_protocol_is_runtime_checkable_and_satisfied_structurally() -> None:
    assert isinstance(_FakeTransportForProtocolCheck(), GitHubActionsTransport)


def test_transport_protocol_rejects_objects_missing_methods() -> None:
    class _Incomplete:
        def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
            return None

    assert not isinstance(_Incomplete(), GitHubActionsTransport)
