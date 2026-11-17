import os

import pytest

from security.paths import AllowedRoots, PathSecurityError


@pytest.fixture
def roots(tmp_path):
    allowed = tmp_path / "allowed"
    (allowed / "sub").mkdir(parents=True)
    (allowed / "file.txt").write_text("x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    return AllowedRoots([allowed]), allowed, outside


def test_normal_file_allowed(roots):
    ar, allowed, _ = roots
    assert ar.safe_resolve(allowed / "file.txt") == (allowed / "file.txt").resolve()


def test_relative_path_resolves_against_root(roots):
    ar, allowed, _ = roots
    assert ar.safe_resolve("file.txt") == (allowed / "file.txt").resolve()


def test_dotdot_escape_denied(roots):
    ar, allowed, outside = roots
    with pytest.raises(PathSecurityError):
        ar.safe_resolve(allowed / ".." / "outside" / "secret.txt")


def test_deep_dotdot_escape_denied(roots):
    ar, allowed, _ = roots
    with pytest.raises(PathSecurityError):
        ar.safe_resolve("../../../Windows/System32/drivers/etc/hosts")


def test_absolute_outside_root_denied(roots):
    ar, _, outside = roots
    with pytest.raises(PathSecurityError):
        ar.safe_resolve(outside / "secret.txt")


def test_root_itself_allowed(roots):
    ar, allowed, _ = roots
    assert ar.safe_resolve(allowed) == allowed.resolve()


def test_symlink_escape_denied(roots, tmp_path):
    ar, allowed, outside = roots
    link = allowed / "evil_link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks require elevated privileges on this machine")
    with pytest.raises(PathSecurityError):
        ar.safe_resolve(link / "secret.txt")


def test_removed_root_denied(roots):
    ar, allowed, _ = roots
    ar.remove(allowed)
    assert not ar.is_allowed(allowed / "file.txt")


def test_missing_root_rejected(tmp_path):
    with pytest.raises(PathSecurityError):
        AllowedRoots([tmp_path / "nonexistent"])


def test_file_root_allows_the_file_only(tmp_path):
    """A single file may be registered as an allowed root (share-a-file)."""
    f = tmp_path / "afile"
    f.write_text("x")
    ar = AllowedRoots([f])
    assert ar.is_allowed(f)
    assert not ar.is_allowed(tmp_path / "other.txt")
