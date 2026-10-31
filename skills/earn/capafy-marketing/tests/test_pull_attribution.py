#!/usr/bin/env python3
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pull_attribution.py"
SPEC = importlib.util.spec_from_file_location("pull_attribution", SCRIPT)
pull_attribution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pull_attribution)


class PullAttributionTests(unittest.TestCase):
    def test_fetches_stats_joins_sales_and_appends_one_daily_row(self):
        stats_response = io.BytesIO(json.dumps({"1": 4, "2": 0}).encode())
        sales_payload = {
            "data": [
                {"agentId": 1, "name": "Writer", "sales": 7},
                {"agentId": "2", "name": "Planner", "sales": 3},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "capafy-attribution.jsonl"
            with (
                patch.object(pull_attribution.request, "urlopen", return_value=stats_response) as urlopen,
                patch.object(pull_attribution, "_fetch_agents", return_value=sales_payload),
            ):
                result = pull_attribution.pull(
                    stats_url="https://landing.example/go-stats",
                    output_file=output,
                    today=date(2026, 7, 19),
                )

            urlopen.assert_called_once()
            request_arg = urlopen.call_args.args[0]
            self.assertEqual(request_arg.full_url, "https://landing.example/go-stats?detail=1")
            self.assertEqual(result["date"], "2026-07-19")
            self.assertFalse(result["causal_claim"])
            self.assertEqual(result["attribution_status"], "candidate_no_order_level_source")
            self.assertEqual(
                result["agents"],
                [
                    {
                        "agent_id": "1",
                        "name": "Writer",
                        "post_urls": [],
                        "cumulative_clicks": 4,
                        "cumulative_sales": 7,
                        "window_clicks": None,
                        "window_sales": None,
                        "tracked_clicks": [],
                        "subscription_orders": None,
                        "attribution_status": "candidate_no_order_level_source",
                    },
                    {
                        "agent_id": "2",
                        "name": "Planner",
                        "post_urls": [],
                        "cumulative_clicks": 0,
                        "cumulative_sales": 3,
                        "window_clicks": None,
                        "window_sales": None,
                        "tracked_clicks": [],
                        "subscription_orders": None,
                        "attribution_status": "candidate_no_order_level_source",
                    },
                ],
            )
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)

    def test_second_pull_on_same_date_does_not_append(self):
        existing = {"date": "2026-07-19", "agents": []}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "capafy-attribution.jsonl"
            output.write_text(json.dumps(existing) + "\n", encoding="utf-8")

            result = pull_attribution.pull(
                output_file=output,
                today=date(2026, 7, 19),
            )

            self.assertEqual(result, existing)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)

    def test_joins_posts_and_computes_noncausal_window_deltas(self):
        previous = {
            "date": "2026-07-18",
            "agents": [
                {"agent_id": "1", "cumulative_clicks": 2, "cumulative_sales": 5},
            ],
        }
        stats_response = io.BytesIO(json.dumps({"1": 4}).encode())
        sales_payload = {"data": [{"agentId": "1", "name": "Writer", "sales": 7}]}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "capafy-attribution.jsonl"
            posts = Path(tmp) / "capafy-marketing-ig-ledger.jsonl"
            output.write_text(json.dumps(previous) + "\n", encoding="utf-8")
            posts.write_text(
                json.dumps(
                    {
                        "agent_id": "1",
                        "reel_url": "https://www.instagram.com/reel/example/",
                        "published_at": "2026-07-19T03:04:05Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                patch.object(pull_attribution.request, "urlopen", return_value=stats_response),
                patch.object(pull_attribution, "_fetch_agents", return_value=sales_payload),
            ):
                result = pull_attribution.pull(
                    stats_url="https://landing.example/go-stats",
                    output_file=output,
                    posts_file=posts,
                    today=date(2026, 7, 19),
                )

            agent = result["agents"][0]
            self.assertEqual(agent["post_urls"], ["https://www.instagram.com/reel/example/"])
            self.assertEqual(agent["window_clicks"], 2)
            self.assertEqual(agent["window_sales"], 2)
            self.assertIsNone(agent["subscription_orders"])
            self.assertFalse(result["causal_claim"])

    def test_detail_stats_report_tracked_urls_and_platform_counts(self):
        detail = {
            "total": 3,
            "platforms": {"legacy": 1, "x": 2},
            "agents": {"1": {"total": 3, "platforms": {"legacy": 1, "x": 2}, "posts": {"x/x-hook": 2}}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(pull_attribution.request, "urlopen", return_value=io.BytesIO(json.dumps(detail).encode())),
                patch.object(pull_attribution, "_fetch_agents", return_value={"data": []}),
            ):
                result = pull_attribution.pull(
                    stats_url="https://landing.example/go-stats",
                    output_file=Path(tmp) / "out.jsonl",
                    posts_file=Path(tmp) / "none.jsonl",
                    today=date(2026, 10, 31),
                )
        self.assertEqual(result["clicks_total"], 3)
        self.assertEqual(result["clicks_by_platform"], {"legacy": 1, "x": 2})
        (agent,) = result["agents"]
        self.assertEqual(agent["cumulative_clicks"], 3)
        self.assertEqual(
            agent["tracked_clicks"],
            [{"url": "https://landing.example/go/1/x/x-hook", "platform": "x", "clicks": 2}],
        )


if __name__ == "__main__":
    unittest.main()
