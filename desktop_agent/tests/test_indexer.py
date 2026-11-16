from indexing.indexer import (
    index_folder,
    list_folder_children,
    register_folder,
    search_files,
)


def _indexed(conn, tree):
    fid = register_folder(conn, tree, label="proj")
    stats = index_folder(conn, fid)
    return fid, stats


def test_indexes_files_and_ignores_defaults(conn, sample_tree):
    fid, stats = _indexed(conn, sample_tree)
    assert stats.added == 5  # main.py, Navbar.tsx, proposal.docx, report.pdf, README.md

    names = {r["name"] for r in conn.execute(
        "SELECT name FROM files WHERE folder_id=? AND deleted=0", (fid,)
    )}
    assert "index.js" not in names       # node_modules ignored
    assert "BUILD_ID" not in names       # .next ignored
    assert "HEAD" not in names           # .git ignored
    assert ".env" not in names           # secrets never indexed


def test_search_by_name(conn, sample_tree):
    _indexed(conn, sample_tree)
    hits = search_files(conn, "proposal")
    assert len(hits) == 1
    assert hits[0]["name"] == "proposal.docx"
    assert hits[0]["file_id"]            # stable id present


def test_search_prefix_and_ext(conn, sample_tree):
    _indexed(conn, sample_tree)
    assert {h["name"] for h in search_files(conn, "repo")} == {"report.pdf"}
    pdfs = search_files(conn, "", ext="pdf")
    assert {p["name"] for p in pdfs} == {"report.pdf"}


def test_search_special_chars_dont_crash(conn, sample_tree):
    _indexed(conn, sample_tree)
    # FTS5 syntax characters in user input must not raise
    assert search_files(conn, 'NEAR/1 " OR *') == []


def test_reindex_detects_modify_and_delete(conn, sample_tree):
    fid, _ = _indexed(conn, sample_tree)
    (sample_tree / "README.md").write_text("# changed and much longer")
    (sample_tree / "docs" / "report.pdf").unlink()

    stats = index_folder(conn, fid)
    assert stats.updated == 1
    assert stats.deleted == 1
    assert search_files(conn, "report") == []


def test_stable_file_id_on_content_change(conn, sample_tree):
    fid, _ = _indexed(conn, sample_tree)
    before = search_files(conn, "Navbar")[0]["file_id"]
    (sample_tree / "src" / "Navbar.tsx").write_text("export default () => null")
    index_folder(conn, fid)
    assert search_files(conn, "Navbar")[0]["file_id"] == before


def test_revisions_recorded(conn, sample_tree):
    fid, _ = _indexed(conn, sample_tree)
    revs = conn.execute("SELECT COUNT(*) c FROM file_revisions").fetchone()["c"]
    assert revs == 5
    (sample_tree / "README.md").write_text("v2")
    index_folder(conn, fid)
    assert conn.execute("SELECT COUNT(*) c FROM file_revisions").fetchone()["c"] == 6


def test_list_children(conn, sample_tree):
    fid, _ = _indexed(conn, sample_tree)
    top = list_folder_children(conn, fid)
    names = {c["name"] for c in top}
    assert {"src", "docs"} <= names                      # dirs surfaced
    assert "README.md" in names
    src = list_folder_children(conn, fid, prefix="src")
    assert {c["name"] for c in src} == {"main.py", "Navbar.tsx"}
