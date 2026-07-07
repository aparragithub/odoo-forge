from odoo_forge.ports.source_provider import SourceProvider


class _FakeGitProvider:
    """Structural stand-in — not a real adapter, just satisfies the shape."""

    def resolve_ref(self, url: str, ref: str) -> str:
        return f"sha-for-{url}@{ref}"


def test_conforming_class_satisfies_source_provider_protocol() -> None:
    provider = _FakeGitProvider()

    assert isinstance(provider, SourceProvider)
    assert provider.resolve_ref("https://github.com/odoo/odoo.git", "19.0") == (
        "sha-for-https://github.com/odoo/odoo.git@19.0"
    )


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _NotAProvider:
        pass

    assert not isinstance(_NotAProvider(), SourceProvider)
