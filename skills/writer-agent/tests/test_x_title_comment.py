from __future__ import annotations

import importlib.util
from pathlib import Path


PARSER = Path(__file__).parents[1] / "scripts" / "x-publish" / "parse_markdown.py"
SPEC = importlib.util.spec_from_file_location("writer_x_markdown_parser_comment", PARSER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_html_title_comment_is_not_used_as_x_article_title(tmp_path: Path) -> None:
    source = tmp_path / "article.md"
    source.write_text(
        '<!-- title: Comment title -->\n\n'
        '# Real X Article title\n\n'
        'Body text.\n',
        encoding="utf-8",
    )

    parsed = MODULE.parse_markdown_file(str(source))

    assert parsed["title"] == "Real X Article title"
