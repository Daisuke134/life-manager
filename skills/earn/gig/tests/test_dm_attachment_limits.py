from __future__ import annotations

import base64
import importlib.util
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("coconala_dm_collect", SCRIPTS / "coconala_dm_collect.py")
assert SPEC and SPEC.loader
coconala_dm_collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coconala_dm_collect)


def test_status_200_oversize_attachment_reports_size_instead_of_http_error(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(coconala_dm_collect, "MAX_ATTACHMENT_BYTES", 4)
    url = "https://coconala.com/uploaded_files/view/1"

    rows = coconala_dm_collect.store_attachments(
        tmp_path,
        [{"url": url, "status": 200, "bytes": 5, "data_base64": None}],
        [{"url": url, "filename": "buyer.pdf", "side": "buyer"}],
    )

    assert rows[0]["response_bytes"] == 5
    assert rows[0]["error"] == "attachment_size_refused:5"


def test_status_200_attachment_inside_limit_is_saved(tmp_path) -> None:
    url = "https://coconala.com/uploaded_files/view/2"
    payload = b"verified buyer file"

    rows = coconala_dm_collect.store_attachments(
        tmp_path,
        [{
            "url": url,
            "status": 200,
            "bytes": len(payload),
            "data_base64": base64.b64encode(payload).decode("ascii"),
        }],
        [{"url": url, "filename": "buyer.pdf", "side": "buyer"}],
    )

    assert rows[0]["bytes"] == len(payload)
    assert rows[0]["sha256"]
    assert Path(rows[0]["path"]).read_bytes() == payload


def test_dm_reader_supports_current_smartphone_dom_contract() -> None:
    expression = coconala_dm_collect.DM_THREAD_EXPRESSION
    assert ".bl_messages-list" in expression
    assert ".bl_message" in expression
    assert "smartphone/users" in expression
    assert "uploaded_files" in expression
