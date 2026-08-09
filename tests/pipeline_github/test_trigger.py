from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport


def test_trigger_returns_the_dispatched_run_without_a_newest_run_lookup() -> None:
    fake = FakeGitHubActionsTransport(run_id="101")
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )
    spec = PipelineRunSpec(definition="ci.yml", parameters={"env": "staging"})

    result = provider.trigger(spec)

    assert fake.dispatch_calls == [("ci.yml", "main", {"env": "staging"})]
    assert result == PipelineRunRef(run_id="101")


def test_trigger_uses_the_configured_ref_for_a_different_provider() -> None:
    fake = FakeGitHubActionsTransport(run_id="7")
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="release/1.0"
    )
    spec = PipelineRunSpec(definition="deploy.yml", parameters={})

    result = provider.trigger(spec)

    assert fake.dispatch_calls == [("deploy.yml", "release/1.0", {})]
    assert result == PipelineRunRef(run_id="7")
