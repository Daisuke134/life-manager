from pathlib import Path

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "article-resume-pending.sh"


def test_resume_exports_the_runs_frozen_product_before_any_publisher():
    # platform-dispatch.sh refuses every STEP 5 row without these (run 20261023-084641 stalled there).
    source = WORKER.read_text(encoding="utf-8")
    block = source.index('PRODUCT_SELECTION_RECEIPT="$RUN_DIR/gates/product-selection.json"')
    assert source.index('[ -d "$RUN_DIR" ] && [ -f "$STATE_PATH" ] || exit 1') < block
    assert block < source.index('scripts/x-post/publish.py" go')
    assert block < source.index('PROMPT_FILE="$RUN_DIR/gates/pending-resume-')
    tail = source[block:block + 1200]
    assert "export ARTICLE_PRODUCT_ID ARTICLE_PRODUCT_LANDING_URL ARTICLE_PRODUCT_CT" in tail
