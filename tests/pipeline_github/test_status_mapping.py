import pytest

from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunState, PipelineRunStatus
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from tests.pipeline_github.fakes import FakeGitHubActionsTransport

_STATUS_CONCLUSION_TABLE: list[tuple[str, str | None, PipelineRunState]] = [
    ("queued", None, "pending"),
    ("requested", None, "pending"),
    ("waiting", None, "pending"),
    ("pending", None, "pending"),
    ("in_progress", None, "running"),
    ("completed", "success", "succeeded"),
    ("completed", "failure", "failed"),
    ("completed", "timed_out", "failed"),
    ("completed", "startup_failure", "failed"),
    ("completed", "cancelled", "canceled"),
    ("completed", "action_required", "unknown"),
    ("completed", "neutral", "unknown"),
    ("completed", "skipped", "unknown"),
    ("completed", "stale", "unknown"),
    ("completed", None, "unknown"),
    ("some_unrecognized_status", None, "unknown"),
    ("some_unrecognized_status", "success", "unknown"),
]


@pytest.mark.parametrize(("status", "conclusion", "expected_state"), _STATUS_CONCLUSION_TABLE)
def test_status_maps_github_status_conclusion_to_neutral_state(
    status: str, conclusion: str | None, expected_state: PipelineRunState
) -> None:
    fake = FakeGitHubActionsTransport(run_state=(status, conclusion))
    provider = GitHubActionsPipelineProvider(
        transport=fake, owner="acme", repo="widgets", ref="main"
    )

    result = provider.status(PipelineRunRef(run_id="42"))

    assert result == PipelineRunStatus(state=expected_state)
    assert fake.get_run_state_calls == ["42"]
