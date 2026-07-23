import pytest

from odoo_forge_cli import _composition

_ALL_ENV_VARS = {
    "FORGE_PIPELINE_GITHUB_TOKEN": "secret-token-value",
    "FORGE_PIPELINE_GITHUB_OWNER": "acme",
    "FORGE_PIPELINE_GITHUB_REPO": "widget",
    "FORGE_PIPELINE_GITHUB_REF": "main",
}


def _set_all_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ALL_ENV_VARS.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("missing_var", sorted(_ALL_ENV_VARS))
def test_missing_env_var_raises_pipeline_configuration_error(
    missing_var: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_all_env(monkeypatch)
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(_composition.PipelineConfigurationError) as exc_info:
        _composition._make_pipeline_provider()

    assert missing_var in str(exc_info.value)
    assert "secret-token-value" not in str(exc_info.value)


def test_all_env_vars_present_builds_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all_env(monkeypatch)

    from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
    from odoo_forge_pipeline_github.transport import GitHubActionsRestTransport

    provider = _composition._make_pipeline_provider()

    assert isinstance(provider, GitHubActionsPipelineProvider)
    assert isinstance(provider._transport, GitHubActionsRestTransport)
