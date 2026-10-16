import importlib.util
import io
import os
import sys
import urllib.error
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("render_body_diagram", SCRIPTS / "render_body_diagram.py")
assert SPEC and SPEC.loader
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


def _png(width: int, height: int) -> bytes:
    # Noise keeps the PNG above the error-blob byte floor, like a real diagram.
    image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(responses):
    calls = []

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(url)
        for prefix, result in responses.items():
            if url.startswith(prefix):
                if isinstance(result, Exception):
                    raise result
                return _Response(result)
        raise AssertionError(f"unexpected url {url}")

    return urlopen, calls


def _run(tmp_path, monkeypatch, responses):
    source = tmp_path / "body-diagram.mmd"
    source.write_text("flowchart TD\n  a[A] --> b[B]\n", encoding="utf-8")
    out = tmp_path / "candidates" / "body-diagram-candidate.png"
    urlopen, calls = _fake_urlopen(responses)
    monkeypatch.setattr(render.urllib.request, "urlopen", urlopen)
    code = render.main(["--in", str(source), "--out", str(out)])
    return code, out, calls


KROKI = "https://kroki.io/"
INK = "https://mermaid.ink/"


def _http_500(url):
    return urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)


def test_kroki_500_falls_back_to_mermaid_ink(tmp_path, monkeypatch):
    code, out, calls = _run(
        tmp_path, monkeypatch, {KROKI: _http_500(KROKI), INK: _png(1300, 900)}
    )
    assert code == 0
    assert [c.split("/")[2] for c in calls] == ["kroki.io", "mermaid.ink"]
    width, height = Image.open(out).size
    assert 110 <= 587 * height / width <= 650


def test_tall_diagram_is_padded_into_x_window(tmp_path, monkeypatch):
    code, out, _ = _run(tmp_path, monkeypatch, {KROKI: _png(276, 558)})
    assert code == 0
    width, height = Image.open(out).size
    assert height == 558 and 587 * height / width <= 650


def test_both_renderers_fail_exits_nonzero_without_output(tmp_path, monkeypatch, capsys):
    code, out, _ = _run(
        tmp_path, monkeypatch, {KROKI: _http_500(KROKI), INK: urllib.error.URLError("timed out")}
    )
    assert code != 0
    assert not out.exists()
    err = capsys.readouterr().err
    assert "kroki" in err and "mermaid.ink" in err


def test_tiny_or_invalid_png_is_rejected(tmp_path, monkeypatch, capsys):
    tiny = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(tiny, format="PNG")
    code, out, _ = _run(
        tmp_path, monkeypatch, {KROKI: tiny.getvalue(), INK: b"<html>" + b"x" * 5000}
    )
    assert code != 0
    assert not out.exists()
    err = capsys.readouterr().err
    assert "bytes" in err and "PNG" in err


def test_too_flat_diagram_is_refused(tmp_path, monkeypatch, capsys):
    code, out, _ = _run(tmp_path, monkeypatch, {KROKI: _png(1300, 100), INK: _png(1300, 100)})
    assert code != 0
    assert not out.exists()
    assert "flowchart TD" in capsys.readouterr().err
