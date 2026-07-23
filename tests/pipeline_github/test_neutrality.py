from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec, PipelineRunStatus
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport


def test_trigger_status_logs_return_exactly_the_neutral_types() -> None:
    fake = FakeGitHubActionsTransport(
        run_ids=["55"], run_state=("completed", "success"), run_logs="log text"
    )
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )

    ref = provider.trigger(PipelineRunSpec(definition="ci.yml"))
    status = provider.status(ref)
    logs = provider.logs(ref)

    assert type(ref) is PipelineRunRef
    assert type(status) is PipelineRunStatus
    assert type(logs) is str
    assert not hasattr(ref, "github_run_id")
    assert not hasattr(status, "conclusion")
