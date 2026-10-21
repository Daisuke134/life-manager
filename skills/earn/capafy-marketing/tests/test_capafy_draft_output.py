import json
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capafy_draft_output as output  # noqa: E402


def test_materialize_valid_structured_output_for_wrapper(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    article = "# Buyer guide\n\n" + ("Useful product facts and steps. " * 30)
    caption = "Try this prompt: one topic, one hook. See the example: https://aniccaai.com/blog/example"
    response = run_dir / "draft-response.json"
    response.write_text(json.dumps({
        "article_markdown": article,
        "x_caption": caption,
    }), encoding="utf-8")
    response.chmod(0o600)

    assert output.materialize(response, run_dir)
    assert (run_dir / "article-en.md").read_text(encoding="utf-8") == article.rstrip() + "\n"
    assert (run_dir / "x-caption.txt").read_text(encoding="utf-8") == caption + "\n"
    assert stat.S_IMODE((run_dir / "article-en.md").stat().st_mode) == 0o600
    assert stat.S_IMODE((run_dir / "x-caption.txt").stat().st_mode) == 0o600


def test_materialize_rejects_duplicate_or_extra_fields_without_output(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    response = run_dir / "draft-response.json"
    response.write_text(
        '{"article_markdown":"one","article_markdown":"two","x_caption":"caption"}',
        encoding="utf-8",
    )
    assert not output.materialize(response, run_dir)
    response.write_text(json.dumps({
        "article_markdown": "# Guide\n\n" + ("Useful facts. " * 40),
        "x_caption": "A short caption",
        "extra": "must fail",
    }), encoding="utf-8")
    assert not output.materialize(response, run_dir)
    assert not (run_dir / "article-en.md").exists()
    assert not (run_dir / "x-caption.txt").exists()
