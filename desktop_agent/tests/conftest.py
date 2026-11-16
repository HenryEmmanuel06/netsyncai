import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import connect  # noqa: E402


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "agentdata"


@pytest.fixture
def conn(data_dir):
    c = connect(data_dir)
    yield c
    c.close()


@pytest.fixture
def sample_tree(tmp_path):
    """A small project-like tree for indexing tests."""
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "node_modules" / "junk").mkdir(parents=True)
    (root / ".next").mkdir()
    (root / ".git").mkdir()
    (root / "docs").mkdir()

    (root / "src" / "main.py").write_text("print('hello')")
    (root / "src" / "Navbar.tsx").write_text("export default function Navbar() {}")
    (root / "docs" / "proposal.docx").write_bytes(b"fake-docx-bytes")
    (root / "docs" / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "node_modules" / "junk" / "index.js").write_text("module.exports={}")
    (root / ".next" / "BUILD_ID").write_text("abc")
    (root / ".git" / "HEAD").write_text("ref: main")
    (root / ".env").write_text("SECRET=x")
    (root / "README.md").write_text("# project")
    return root
