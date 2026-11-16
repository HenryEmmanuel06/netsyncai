"""Desktop app-mode helpers that don't need a display."""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desktop.agent_app import parse_pair_link
from desktop.instance import InstanceServer, send_to_running
from main import is_cli


def test_parse_pair_link():
    assert parse_pair_link("netsync://pair?code=ABCD2345") == "ABCD2345"
    assert parse_pair_link("netsync://pair/?code=abcd2345") == "ABCD2345"
    assert parse_pair_link("NETSYNC://pair?code=ABCD2345") == "ABCD2345"


def test_parse_pair_link_rejects_garbage():
    assert parse_pair_link("netsync://pair?code=SHORT") is None
    assert parse_pair_link("netsync://pair?code=AB$D2345") is None
    assert parse_pair_link("netsync://open") is None
    assert parse_pair_link("https://evil.example/pair?code=ABCD2345") is None
    assert parse_pair_link("show") is None


def test_cli_vs_app_mode_detection():
    assert is_cli(["pair", "ABCD2345"])
    assert is_cli(["--data-dir", "x", "run"])
    assert not is_cli([])
    assert not is_cli(["--background"])
    assert not is_cli(["netsync://pair?code=ABCD2345"])


def test_single_instance_handoff(monkeypatch):
    import desktop.instance as inst
    monkeypatch.setattr(inst, "PORT", 47699)

    got = []
    done = threading.Event()

    def on_msg(m):
        got.append(m)
        done.set()

    first = InstanceServer(on_msg)
    assert first.try_acquire()
    try:
        second = InstanceServer(lambda m: None)
        assert not second.try_acquire()          # only one agent per user
        assert send_to_running("netsync://pair?code=ABCD2345")
        assert done.wait(3)
        assert got == ["netsync://pair?code=ABCD2345"]
    finally:
        first.close()
    assert not send_to_running("show")           # nobody listening now
