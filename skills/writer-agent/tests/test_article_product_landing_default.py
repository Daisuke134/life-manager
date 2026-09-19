from pathlib import Path


ARTICLE_DAILY = Path(__file__).resolve().parents[1] / "article-daily.sh"


def test_writer_cta_default_points_at_paid_life_manager_landing_page():
    source = ARTICLE_DAILY.read_text(encoding="utf-8")

    assert (
        'ARTICLE_PRODUCT_LANDING_URL="${ARTICLE_PRODUCT_LANDING_URL:-https://aniccaai.com/lm}"'
        in source
    )
    assert 'ARTICLE_PRODUCT_LANDING_URL="${ARTICLE_PRODUCT_LANDING_URL:-https://aniccaai.com/}"' not in source
