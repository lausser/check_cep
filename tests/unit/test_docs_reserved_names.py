"""The docs list every reserved --environ name and no longer call --environ
authoring-only (spec 023 FR-080, FR-084)."""
from pathlib import Path

from conftest import _cep_mod as cep

_ROOT = Path(__file__).parent.parent.parent


def test_readme_lists_every_reserved_name():
    readme = (_ROOT / "README.md").read_text()
    missing = [n for n in sorted(cep.RESERVED_ENV_NAMES) + list(cep.RESERVED_ENV_PREFIXES)
               if f"`{n}`" not in readme]
    assert not missing, missing


def test_no_authoring_only_environ_statement():
    for doc in ("README.md", "WRITING-TESTS.md"):
        text = (_ROOT / doc).read_text()
        assert "only takes effect with --authoring" not in text, doc
        assert "`--environ`\n  is inert" not in text, doc
