from pathlib import Path


ARTICLE_DAILY = Path(__file__).resolve().parents[1] / "article-daily.sh"


def test_note_eyecatch_prompt_uses_managed_browser_python():
    source = ARTICLE_DAILY.read_text(encoding="utf-8")

    assert (
        "NOTE_KEY=<KEY> WRITER_BROWSER_PYTHON_PLACEHOLDER "
        "ARTICLE_ROOT_PLACEHOLDER/scripts/note-publish/set-eyecatch-draft.py"
    ) in source
    assert (
        "NOTE_KEY=<KEY> python3 "
        "ARTICLE_ROOT_PLACEHOLDER/scripts/note-publish/set-eyecatch-draft.py"
    ) not in source
