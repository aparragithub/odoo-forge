import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / "factory"


def _last_user(dockerfile: str) -> str | None:
    users = re.findall(r"^\s*USER\s+(\S+)\s*(?:#.*)?$", dockerfile, re.MULTILINE | re.IGNORECASE)
    return users[-1] if users else None


def test_last_user_returns_the_final_effective_user() -> None:
    assert _last_user("FROM odoo\nUSER root\nUSER odoo\n") == "odoo"
    assert _last_user("FROM odoo\nUSER odoo\nUSER root\n") == "root"
    assert _last_user("FROM odoo\nRUN true\n") is None


def test_factory_image_wiring_matches_runtime_paths_and_permissions() -> None:
    dockerfile = (FACTORY / "Dockerfile").read_text()
    entrypoint = (FACTORY / "entrypoint.sh").read_text()

    copies = dict(
        re.findall(
            r"^COPY --chown=odoo:odoo (factory/\S+) (\S+)$",
            dockerfile,
            re.MULTILINE,
        )
    )

    assert copies["factory/entrypoint.sh"] == "/entrypoint.sh"
    assert copies["factory/lib/credentials.sh"] == "/lib/credentials.sh"
    assert copies["factory/wait-for-psql.py"] == "/usr/local/bin/wait-for-psql.py"
    assert 'source "$(dirname "$0")/lib/credentials.sh"' in entrypoint
    assert "/usr/local/bin/wait-for-psql.py" in entrypoint
    assert "RUN chmod +x /entrypoint.sh /usr/local/bin/wait-for-psql.py" in dockerfile
    assert _last_user(dockerfile) == "odoo"
    assert 'ENTRYPOINT ["/entrypoint.sh"]' in dockerfile
