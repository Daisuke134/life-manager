import pathlib
import sys
import json

import jsonschema

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intent_store import IntentStore, build_intent
from native_candidates import extract_tiktok_candidates
from publish_cli import run_native_candidates


def test_extracts_exact_handle_candidates_with_canonical_native_receipts():
    payload = {"itemList": [
        {"id": "7468922143619812626", "desc": "lesson ee_token",
         "createTime": 1785632400, "author": {"uniqueId": "obou_anicca"}},
        {"id": "7468922143619812627", "desc": "wrong account ee_token",
         "createTime": 1785632401, "author": {"uniqueId": "someone_else"}},
    ]}
    rows = extract_tiktok_candidates(payload, expected_handle="obou_anicca")
    assert rows == [{
        "native_handle": "obou_anicca",
        "native_post_id": "7468922143619812626",
        "native_post_url": "https://www.tiktok.com/@obou_anicca/video/7468922143619812626",
        "caption": "lesson ee_token",
        "published_at": "2026-08-02T01:00:00Z",
    }]


def test_invalid_ids_timestamps_and_shapes_are_ignored():
    payload = {"itemList": [
        {"id": "short", "desc": "x", "createTime": 1785632400,
         "author": {"uniqueId": "obou_anicca"}},
        {"id": "7468922143619812626", "desc": "x", "createTime": "invalid",
         "author": {"uniqueId": "obou_anicca"}},
        "not-an-object",
    ]}
    assert extract_tiktok_candidates(payload, expected_handle="obou_anicca") == []


def test_duplicate_api_items_collapse_by_native_id():
    item = {"id": "7468922143619812626", "desc": "lesson",
            "createTime": 1785632400, "author": {"uniqueId": "obou_anicca"}}
    rows = extract_tiktok_candidates({"itemList": [item, item]},
                                     expected_handle="obou_anicca")
    assert len(rows) == 1


def tiktok_intent(tmp_path):
    asset = tmp_path / "preview.mp4"
    asset.write_bytes(b"preview")
    return build_intent(
        experiment_id="experiment.tiktok", creative_id="creative.tiktok",
        product_id="ebook-ja", account_id="tiktok.obou_anicca",
        hook_id="hook.tiktok", renderer_id="watercolor-monk", adapter="postiz",
        asset_path=asset,
        caption="読む https://aniccaai.com/go/ej_token ej_token",
        attribution_token="ej_token", scheduled_at="2026-08-02T01:00:00Z",
        integration_id="cmo5s4edx00vgn10ygnu34a0n", platform="tiktok",
        native_handle="obou_anicca",
        provider_settings={"__type": "tiktok", "title": "",
            "privacy_level": "PUBLIC_TO_EVERYONE", "duet": False, "stitch": False,
            "comment": True, "autoAddMusic": "no", "brand_content_toggle": False,
            "brand_organic_toggle": False, "video_made_with_ai": True,
            "content_posting_method": "DIRECT_POST"},
        visual_approval_id="visual.accepted.tiktok")


def test_native_candidate_cli_filters_unrelated_posts_and_writes_schema(tmp_path):
    intent = tiktok_intent(tmp_path)
    store = IntentStore(tmp_path / "jobs.sqlite3")
    store.register(intent)
    exact = {"native_handle": "obou_anicca", "native_post_id": "7468922143619812626",
             "native_post_url": "https://www.tiktok.com/@obou_anicca/video/7468922143619812626",
             "caption": "読む ej_token", "published_at": intent["scheduled_at"]}
    unrelated = exact | {"native_post_id": "7468922143619812627", "caption": "other"}
    observed = {}

    def collector(**kwargs):
        observed.update(kwargs)
        return {"api_responses_observed": 1, "profile_items_observed": 2,
                "candidates": [unrelated, exact]}

    output = tmp_path / "native-candidates.json"
    report = tmp_path / "native-candidates-report.json"
    result = run_native_candidates(
        db_path=store.path, publish_key=intent["publish_key"], output_path=output,
        engine=HERE.parent, cdp_url="http://localhost:9222", wait_ms=1,
        collector=collector, report_path=report)
    assert result["candidate_count"] == 1
    assert result["api_responses_observed"] == 1
    assert result["profile_items_observed"] == 2
    assert observed["expected_handle"] == "obou_anicca"
    rows = json.loads(output.read_text())
    assert rows == [exact]
    report_value = json.loads(report.read_text())
    assert report_value["profile_items_observed"] == 2
    report_schema = json.loads((HERE.parent / "schemas/native-candidate-scan.schema.json").read_text())
    jsonschema.validate(report_value, report_schema)
    schema = json.loads((HERE.parent / "schemas/native-candidates.schema.json").read_text())
    jsonschema.validate(rows, schema)


def test_native_candidate_cli_distinguishes_unobserved_api_from_zero_match(tmp_path):
    intent = tiktok_intent(tmp_path)
    store = IntentStore(tmp_path / "jobs.sqlite3")
    store.register(intent)
    result = run_native_candidates(
        db_path=store.path, publish_key=intent["publish_key"],
        output_path=tmp_path / "none.json", engine=HERE.parent,
        cdp_url="http://localhost:9222", wait_ms=1,
        collector=lambda **_: {"api_responses_observed": 0,
                               "profile_items_observed": 0, "candidates": []})
    assert result["status"] == "collector_unverified"
    assert result["candidate_count"] == 0
