from odoo_forge.pipeline.types import PipelineRunRef
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport


def test_logs_returns_the_transports_plain_log_text() -> None:
    fake = FakeGitHubActionsTransport(run_logs="build step 1\nbuild step 2\ndone")
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )

    result = provider.logs(PipelineRunRef(run_id="99"))

    assert result == "build step 1\nbuild step 2\ndone"
    assert fake.get_run_logs_calls == ["99"]


def test_logs_returns_empty_string_when_run_has_no_output() -> None:
    fake = FakeGitHubActionsTransport(run_logs="")
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )

    result = provider.logs(PipelineRunRef(run_id="1"))

    assert result == ""
    assert fake.get_run_logs_calls == ["1"]
