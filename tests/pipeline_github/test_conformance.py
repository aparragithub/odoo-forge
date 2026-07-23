from odoo_forge.ports.pipeline_provider import PipelineProvider
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport


def test_provider_satisfies_pipeline_provider_protocol() -> None:
    provider = GitHubActionsPipelineProvider(
        transport=FakeGitHubActionsTransport(),
        owner="acme",
        repo="widgets",
        ref="main",
    )

    assert isinstance(provider, PipelineProvider)
