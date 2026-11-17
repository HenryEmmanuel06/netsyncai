"""File-operation tests — run handlers directly against a real DB+tree."""

import asyncio
import base64
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_operations.ops import AgentContext, HANDLERS, OpDenied
from indexing.indexer import index_folder, register_folder
from protocol import Envelope, MessageType


@pytest.fixture
def sent():
    msgs = []

    async def _send(raw: str):
        msgs.append(Envelope.model_validate_json(raw))

    _send.msgs = msgs
    return _send


@pytest.fixture
def rw_ctx(conn, sample_tree, sent):
    register_folder(conn, sample_tree, access="readwrite")
    index_folder(conn, 1)
    return AgentContext(conn, sent)


@pytest.fixture
def ro_ctx(conn, sample_tree, sent):
    register_folder(conn, sample_tree, access="read")
    index_folder(conn, 1)
    return AgentContext(conn, sent)


# ── browse/search ────────────────────────────────────────────────────────────

async def test_browse_roots(rw_ctx, sample_tree):
    res = await HANDLERS["browse_folder"](rw_ctx, {"path": ""})
    assert res["roots"][0]["path"] == str(sample_tree.resolve())
    assert res["roots"][0]["access"] == "readwrite"


async def test_browse_dir(rw_ctx, sample_tree):
    res = await HANDLERS["browse_folder"](rw_ctx, {"path": str(sample_tree)})
    names = {e["name"] for e in res["entries"]}
    assert {"src", "docs", "README.md"} <= names
    # ignored dirs still exist on disk and DO appear in browse (browse is
    # the filesystem; ignores apply to the search index only)


async def test_browse_traversal_denied(rw_ctx, sample_tree):
    with pytest.raises(OpDenied):
        await HANDLERS["browse_folder"](
            rw_ctx, {"path": str(sample_tree / ".." / "..")}
        )


async def test_search(rw_ctx):
    res = await HANDLERS["search_files"](rw_ctx, {"query": "proposal"})
    assert res["results"][0]["name"] == "proposal.docx"


# ── write-op access control ─────────────────────────────────────────────────

async def test_rename_on_readwrite(rw_ctx, sample_tree):
    f = sample_tree / "README.md"
    await HANDLERS["rename_file"](
        rw_ctx, {"path": str(f), "new_name": "RENAMED.md"}
    )
    assert (sample_tree / "RENAMED.md").exists()
    assert not f.exists()


async def test_rename_on_readonly_denied(ro_ctx, sample_tree):
    with pytest.raises(OpDenied):
        await HANDLERS["rename_file"](
            ro_ctx, {"path": str(sample_tree / "README.md"), "new_name": "x.md"}
        )


async def test_rename_traversal_denied(rw_ctx, sample_tree):
    with pytest.raises(OpDenied):
        await HANDLERS["rename_file"](
            rw_ctx,
            {"path": str(sample_tree / ".." / "outside.txt"), "new_name": "x"},
        )


async def test_rename_name_sanitized(rw_ctx, sample_tree):
    with pytest.raises(OpDenied):
        await HANDLERS["rename_file"](
            rw_ctx,
            {"path": str(sample_tree / "README.md"), "new_name": "..\\evil"},
        )


async def test_delete_on_readonly_denied(ro_ctx, sample_tree):
    with pytest.raises(OpDenied):
        await HANDLERS["delete_file"](
            ro_ctx, {"path": str(sample_tree / "README.md")}
        )


async def test_delete_file(rw_ctx, sample_tree):
    await HANDLERS["delete_file"](
        rw_ctx, {"path": str(sample_tree / "docs" / "report.pdf")}
    )
    assert not (sample_tree / "docs" / "report.pdf").exists()


async def test_mkdir(rw_ctx, sample_tree):
    await HANDLERS["create_folder"](
        rw_ctx, {"path": str(sample_tree / "new" / "nested")}
    )
    assert (sample_tree / "new" / "nested").is_dir()


async def test_move_and_copy(rw_ctx, sample_tree):
    await HANDLERS["create_folder"](
        rw_ctx, {"path": str(sample_tree / "dest")}
    )
    await HANDLERS["move_file"](rw_ctx, {
        "src": str(sample_tree / "README.md"),
        "dst": str(sample_tree / "dest" / "README.md"),
    })
    assert (sample_tree / "dest" / "README.md").exists()
    await HANDLERS["copy_file"](rw_ctx, {
        "src": str(sample_tree / "dest" / "README.md"),
        "dst": str(sample_tree / "dest" / "COPY.md"),
    })
    assert (sample_tree / "dest" / "COPY.md").exists()


# ── transfers ────────────────────────────────────────────────────────────────

async def test_download_streams_verified_chunks(rw_ctx, sample_tree, sent):
    target = sample_tree / "docs" / "proposal.docx"
    await HANDLERS["download_file"](
        rw_ctx, {"path": str(target), "transfer_id": "t1"}
    )
    envs = sent.msgs
    assert envs[0].type is MessageType.TRANSFER_BEGIN
    body = b"".join(
        base64.b64decode(e.payload["data"])
        for e in envs if e.type is MessageType.TRANSFER_CHUNK
    )
    end = next(e for e in envs if e.type is MessageType.TRANSFER_END)
    assert body == target.read_bytes()
    assert hashlib.sha256(body).hexdigest() == end.payload["sha256"]


async def test_download_dir_streams_zip(rw_ctx, sample_tree, sent):
    await HANDLERS["download_file"](
        rw_ctx, {"path": str(sample_tree / "docs"), "transfer_id": "tz"}
    )
    envs = sent.msgs
    begin = envs[0]
    assert begin.type is MessageType.TRANSFER_BEGIN
    assert begin.payload["name"] == "docs.zip"
    body = b"".join(
        base64.b64decode(e.payload["data"])
        for e in envs if e.type is MessageType.TRANSFER_CHUNK
    )
    end = next(e for e in envs if e.type is MessageType.TRANSFER_END)
    assert hashlib.sha256(body).hexdigest() == end.payload["sha256"]
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = z.namelist()
    assert "docs/report.pdf" in names and "docs/proposal.docx" in names


async def test_send_file_writes_atomically(rw_ctx, sample_tree, sent):
    payload = b"hello upload " * 5000
    digest = hashlib.sha256(payload).hexdigest()
    state = rw_ctx.transfer_state("up1")

    handler = asyncio.create_task(HANDLERS["send_file"](
        rw_ctx, {"path": str(sample_tree / "upload.bin"), "transfer_id": "up1"}
    ))
    await asyncio.sleep(0)  # let handler register + open tmp
    await state.queue.put(Envelope(
        type=MessageType.TRANSFER_CHUNK,
        payload={"transfer_id": "up1", "seq": 0,
                 "data": base64.b64encode(payload).decode()},
    ))
    await state.queue.put(Envelope(
        type=MessageType.TRANSFER_END,
        payload={"transfer_id": "up1", "seq": 1, "sha256": digest},
    ))
    res = await handler
    assert res["sha256"] == digest
    assert Path(res["written"]).read_bytes() == payload
    # no partial files left
    assert not list(sample_tree.glob(".netsync-partial/*"))


async def test_send_file_corrupted_rejected(rw_ctx, sample_tree):
    state = rw_ctx.transfer_state("up2")
    handler = asyncio.create_task(HANDLERS["send_file"](
        rw_ctx, {"path": str(sample_tree / "bad.bin"), "transfer_id": "up2"}
    ))
    await asyncio.sleep(0)
    await state.queue.put(Envelope(
        type=MessageType.TRANSFER_CHUNK,
        payload={"transfer_id": "up2", "seq": 0,
                 "data": base64.b64encode(b"garbage").decode()},
    ))
    await state.queue.put(Envelope(
        type=MessageType.TRANSFER_END,
        payload={"transfer_id": "up2", "seq": 1, "sha256": "0" * 64},
    ))
    with pytest.raises(OpDenied, match="sha256"):
        await handler
    assert not (sample_tree / "bad.bin").exists()


async def test_send_file_collision_renames(rw_ctx, sample_tree):
    payload = b"dup"
    digest = hashlib.sha256(payload).hexdigest()

    async def push(tid):
        state = rw_ctx.transfer_state(tid)
        h = asyncio.create_task(HANDLERS["send_file"](
            rw_ctx, {"path": str(sample_tree / "README.md"), "transfer_id": tid}
        ))
        await asyncio.sleep(0)
        await state.queue.put(Envelope(
            type=MessageType.TRANSFER_CHUNK,
            payload={"transfer_id": tid, "seq": 0,
                     "data": base64.b64encode(payload).decode()},
        ))
        await state.queue.put(Envelope(
            type=MessageType.TRANSFER_END,
            payload={"transfer_id": tid, "seq": 1, "sha256": digest},
        ))
        return await h

    r1 = await push("u1")
    assert "README (1).md" in r1["written"]   # README.md already exists


async def test_sys_info(rw_ctx):
    res = await HANDLERS['sys_info'](rw_ctx, {})
    assert 'platform' in res and 'libreoffice' in res
    assert any(d['drive'] for d in res['drives'])


async def test_convert_denies_when_no_soffice(rw_ctx, sample_tree, monkeypatch):
    monkeypatch.setattr('file_operations.ops._soffice', lambda: None)
    try:
        await HANDLERS['convert_document'](rw_ctx, {'path': str(sample_tree / 'README.md')})
        assert False
    except OpDenied as e:
        assert 'LibreOffice' in str(e)


async def test_convert_requires_write_access(ro_ctx, sample_tree):
    try:
        await HANDLERS['convert_document'](ro_ctx, {'path': str(sample_tree / 'README.md')})
        assert False
    except OpDenied:
        pass
