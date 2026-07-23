import socket

import pytest

from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport


@pytest.fixture
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted during a hermetic test")

    monkeypatch.setattr(socket, "socket", _raise)
    monkeypatch.setattr(socket, "create_connection", _raise)


def test_trigger_status_logs_never_touch_the_network(block_network: None) -> None:
    fake = FakeGitHubActionsTransport(
        run_ids=["1"], run_state=("in_progress", None), run_logs="hermetic log"
    )
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )

    ref = provider.trigger(PipelineRunSpec(definition="ci.yml"))
    provider.status(ref)
    provider.logs(ref)

    assert ref == PipelineRunRef(run_id="1")
    assert fake.dispatch_calls == [("ci.yml", "main", {})]
