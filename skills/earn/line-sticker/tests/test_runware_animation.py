"""Subprocess contract tests for the Runware animation adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from threading import Thread


MODULE_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = MODULE_ROOT / "runware_animation.py"
SPEC = importlib.util.spec_from_file_location("runware_animation", ADAPTER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MEDIA_UUID = "12345678-1234-4234-8234-1234567890ab"
API_KEY = "runware-test-secret-never-output"
MODEL = "prunaai:p-video@0"


class _DetailsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.redirect_followed = True
        self.send_response(200); self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        self.server.headers.append(self.headers.get("Authorization", ""))
        if self.server.redirect and self.path == "/redirect":
            self.send_response(302); self.send_header("Location", self.server.redirect_target); self.end_headers(); return
        if self.path == "/v1" and self.server.redirect:
            self.server.redirect_followed = True
        self.server.requests.append(request)
        if self.server.fail:
            self.send_response(500); self.end_headers(); return
        task = request[0]["taskUUID"]
        if self.server.insufficient:
            response = {"errors": [{"code": "videoInferenceInsufficientCredits", "message": "requires paid invoice", "taskType": self.server.error_task_type, "taskUUID": task}]}
        else:
            video = "\u0000invalid" if self.server.invalid else str(self.server.video)
            response = {"data": [{"taskType": "videoInference", "taskUUID": task, "videoURL": video, "cost": "0.05", "status": "success"}]}
        if self.server.mixed:
            response["errors"] = [{"code": "also-an-error", "taskType": "videoInference", "taskUUID": task}]
        body = json.dumps({"data": [{"taskType": self.server.outer_task_type, "taskUUID": self.server.outer_task_uuid or task,
                                      "request": [{"taskType": self.server.request_task_type, "model": self.server.request_model,
                                                    "taskUUID": self.server.request_task_uuid or task}], "response": response}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


class RunwareAnimationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runware-animation-test-")
        self.root = Path(self.temp.name)
        self.character = self.root / "character.png"
        self.character.write_bytes(b"character-reference")
        self.video = self.root / "fake-video.mp4"
        self.video.write_bytes(b"fake-mp4")
        self.log = self.root / "provider.jsonl"
        self.fake = self.root / "fake-runware"
        self.fake.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import json
                import os
                from pathlib import Path
                import sys

                operation = sys.argv[1] if len(sys.argv) > 1 else ""
                with Path(os.environ["RUNWARE_FAKE_LOG"]).open("a", encoding="utf-8") as stream:
                    json.dump({"argv": sys.argv[1:]}, stream)
                    stream.write("\\n")
                if operation == "model":
                    print(json.dumps({"air": "prunaai:p-video@0", "status": "live", "pricingExamples": [
                      {"configuration": "720p · 1s · DRAFT MODE", "price": "$0.005"}]}))
                elif operation == "run":
                    task = next(value.split("=", 1)[1] for value in sys.argv if value.startswith("taskUUID="))
                    print(json.dumps({"taskUUID": task, "videoURL": os.environ["RUNWARE_FAKE_VIDEO"], "cost": 0.05}))
                elif operation == "result":
                    if os.environ.get("RUNWARE_FAKE_FAIL") == "1":
                        raise SystemExit(9)
                    video = chr(0) + "invalid" if os.environ.get("RUNWARE_FAKE_INVALID") == "1" else os.environ["RUNWARE_FAKE_VIDEO"]
                    print(json.dumps({"taskUUID": sys.argv[2], "videoURL": video, "cost": "0.05"}))
                else:
                    raise SystemExit(8)
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _DetailsHandler)
        self.server.requests, self.server.video = [], self.video
        self.server.headers = []
        self.server.fail = self.server.invalid = self.server.insufficient = self.server.mixed = False
        self.server.redirect = self.server.redirect_followed = False
        self.server.redirect_target = ""
        self.server.outer_task_type = "getTaskDetails"
        self.server.outer_task_uuid = ""
        self.server.request_task_type = "videoInference"
        self.server.request_model = "prunaai:p-video@0"
        self.server.request_task_uuid = ""
        self.server.error_task_type = "videoInference"
        self.thread = Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        self.temp.cleanup()

    def _env(self, *, fail_reconcile: bool = False, invalid_reconcile: bool = False, api_url: str | None = None) -> dict[str, str]:
        env = dict(__import__("os").environ)
        env.update(
            {
                "RUNWARE_API_KEY": API_KEY,
                "LINE_STICKER_RUNWARE_MEDIA_UUID": MEDIA_UUID,
                "LINE_STICKER_RUNWARE_BIN": str(self.fake),
                "RUNWARE_FAKE_LOG": str(self.log),
                "RUNWARE_FAKE_VIDEO": str(self.video),
                "LINE_STICKER_RUNWARE_API_URL": api_url or f"http://127.0.0.1:{self.server.server_port}/v1",
            }
        )
        if fail_reconcile:
            self.server.fail = True
        else:
            env.pop("RUNWARE_FAKE_FAIL", None)
        if invalid_reconcile:
            self.server.invalid = True
        else:
            env.pop("RUNWARE_FAKE_INVALID", None)
        return env

    def _run(self, request: dict[str, object], *, fail_reconcile: bool = False, invalid_reconcile: bool = False, api_url: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ADAPTER)],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            cwd=self.root,
            env=self._env(fail_reconcile=fail_reconcile, invalid_reconcile=invalid_reconcile, api_url=api_url),
        )

    def _quote_request(self) -> dict[str, object]:
        return {
            "version": 1,
            "operation": "quote",
            "set_id": "set-1",
            "character_id": "char-1",
            "character_sha256": hashlib.sha256(self.character.read_bytes()).hexdigest(),
            "plan_sha256": "a" * 64,
            "batch": 1,
            "motions": [
                {
                    "motion_id": f"motion-{index:02d}",
                    "batch": 1,
                    "position": index,
                    "intent": f"intent {index}",
                    "action": f"action {index}",
                    "provider_prompt": f"provider motion {index}",
                    "duration_ms": 1000,
                }
                for index in range(1, 11)
            ],
        }

    def _generate_request(self, quote: dict[str, object]) -> dict[str, object]:
        request = self._quote_request()
        request.update(
            {
                "operation": "generate",
                "character_path": str(self.character),
                "remaining_cap_usd": "0.05",
                "request_id": quote["request_id"],
                "quote_token": quote["quote_token"],
                "provider": quote["provider"],
                "model": quote["model"],
            }
        )
        return request

    def _reconcile_request(self, quote: dict[str, object]) -> dict[str, object]:
        return {
            "version": 1,
            "operation": "reconcile",
            "request_id": quote["request_id"],
            "quote_token": quote["quote_token"],
            "batch": quote["batch"],
            "provider": quote["provider"],
            "model": quote["model"],
        }

    def _json_stdout(self, process: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(process.stdout.count("\n"), 1, process.stdout)
        value = json.loads(process.stdout)
        self.assertIsInstance(value, dict)
        return value

    def _assert_secret_absent(self, process: subprocess.CompletedProcess[str]) -> None:
        self.assertNotIn(API_KEY, process.stdout)
        self.assertNotIn(API_KEY, process.stderr)

    def test_quote_reads_official_pricing_and_is_deterministic(self) -> None:
        request = self._quote_request()
        first_process = self._run(request)
        second_process = self._run(request)
        self.assertEqual(first_process.returncode, 0, first_process.stderr)
        self.assertEqual(second_process.returncode, 0, second_process.stderr)
        first = self._json_stdout(first_process)
        second = self._json_stdout(second_process)
        self.assertEqual(
            set(first),
            {"request_id", "quote_token", "batch", "provider", "model", "quoted_cost_usd", "expires_at", "regenerable"},
        )
        self.assertEqual(first, second)
        self.assertEqual(str(uuid.UUID(str(first["request_id"]))), first["request_id"])
        expiry = datetime.fromisoformat(str(first["expires_at"]).replace("Z", "+00:00"))
        self.assertIsNotNone(expiry.tzinfo)
        self.assertGreater(expiry.astimezone(timezone.utc), datetime.now(timezone.utc))
        self.assertEqual(first["quoted_cost_usd"], "0.05")
        self.assertEqual(first["provider"], "runware")
        self.assertEqual(first["model"], "prunaai:p-video@0")
        self.assertFalse(first["regenerable"])
        invocations = [json.loads(line)["argv"] for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(invocations, [["model", "pricing", "prunaai:p-video@0", "--format", "json"]] * 2)
        self._assert_secret_absent(first_process)
        self._assert_secret_absent(second_process)

    def test_tampered_quote_token_is_rejected_without_secret_output(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json_stdout(quote_process)
        request = self._generate_request(quote)
        token = str(request["quote_token"])
        request["quote_token"] = token[:-1] + ("0" if token[-1] != "0" else "1")
        process = self._run(request)
        self.assertNotEqual(process.returncode, 0)
        error = self._json_stdout(process)
        self.assertIn("error", error)
        self.assertNotIn("secret", json.dumps(error).lower())
        invocations = [json.loads(line)["argv"] for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(invocations, [["model", "pricing", "prunaai:p-video@0", "--format", "json"]])
        self._assert_secret_absent(process)

    def test_generate_uses_exact_runware_argv_and_returns_hashed_ten_segments(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json_stdout(quote_process)
        process = self._run(self._generate_request(quote))
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self._json_stdout(process)
        self.assertEqual(
            set(result),
            {"request_id", "quote_token", "batch", "provider", "model", "acknowledged", "video_path", "video_sha256", "segments", "regenerable", "actual_cost_usd"},
        )
        self.assertTrue(result["acknowledged"])
        self.assertFalse(result["regenerable"])
        output = Path(str(result["video_path"]))
        self.assertEqual(output, (self.root / "source-batch-1.mp4").resolve())
        self.assertEqual(result["video_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(result["actual_cost_usd"], "0.05")
        self.assertEqual(
            result["segments"],
            [
                {"motion_id": f"motion-{index:02d}", "start_ms": (index - 1) * 1000, "end_ms": index * 1000}
                for index in range(1, 11)
            ],
        )
        invocation = json.loads(self.log.read_text(encoding="utf-8").splitlines()[-1])["argv"]
        prompt = ""
        for item in invocation:
            if item.startswith("positivePrompt="):
                prompt = item.split("=", 1)[1]
                break
        expected = [
            "run",
            "prunaai:p-video@0",
            "--task-type",
            "videoInference",
            "--delivery-method",
            "async",
            "--format",
            "json",
            "--no-download",
            "--validate",
            f"positivePrompt={prompt}",
            "resolution=720p",
            "duration=10",
            "fps=24",
            f"inputs.frameImages.0={MEDIA_UUID}",
            "settings.audio=false",
            "settings.draft=true",
            "settings.promptUpsampling=false",
            "includeCost=true",
            "numberResults=1",
            "outputFormat=MP4",
            f"taskUUID={quote['request_id']}",
        ]
        self.assertEqual(invocation, expected)
        self.assertIn("0-1s:", prompt)
        self.assertIn("9-10s:", prompt)
        self.assertIn("solid #00FF00", prompt)
        self.assertIn("one centered character", prompt)
        self.assertIn("no text", prompt)
        self.assertIn("no logo", prompt)
        self.assertIn("no cuts", prompt)
        for index in range(1, 11):
            self.assertIn(f"provider motion {index}", prompt)
        self._assert_secret_absent(process)

    def test_invalid_motion_id_returns_stable_json_without_generation(self) -> None:
        request = self._quote_request()
        request["motions"][0]["motion_id"] = "motion--1"
        process = self._run(request)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self._json_stdout(process), {"error": "adapter_error"})
        self.assertNotIn("Traceback", process.stderr)
        self.assertFalse(self.log.exists())
        self._assert_secret_absent(process)

    def test_reconcile_completed_uses_result_without_run(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json_stdout(quote_process)
        process = self._run(self._reconcile_request(quote))
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self._json_stdout(process)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["actual_cost_usd"], "0.05")
        self.assertEqual(len(result["segments"]), 10)
        self.assertEqual(result["video_path"], str((self.root / "source-batch-1.mp4").resolve()))
        invocations = [json.loads(line)["argv"] for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(invocations, [["model", "pricing", "prunaai:p-video@0", "--format", "json"]])
        self.assertEqual(self.server.requests[-1], [{"taskType": "getTaskDetails", "taskUUID": quote["request_id"]}])
        self._assert_secret_absent(process)

    def test_expired_signed_token_still_reconciles_but_cannot_generate(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        payload = MODULE._decode(quote["quote_token"], API_KEY)
        payload["expires_at"] = "2000-01-01T00:00:00Z"
        expired = MODULE._token(payload, API_KEY)
        quote["quote_token"] = expired
        generate = self._run(self._generate_request(quote))
        self.assertNotEqual(generate.returncode, 0)
        before = len(self.server.requests)
        reconciled = self._run(self._reconcile_request(quote))
        result = self._json_stdout(reconciled)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.server.requests[before:], [[{"taskType": "getTaskDetails", "taskUUID": quote["request_id"]}]])
        self._assert_secret_absent(generate)
        self._assert_secret_absent(reconciled)

    def test_failed_reconcile_returns_unknown_and_never_runs_generation(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json_stdout(quote_process)
        process = self._run(self._reconcile_request(quote), fail_reconcile=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self._json_stdout(process)
        self.assertEqual(
            result,
            {
                "request_id": quote["request_id"],
                "quote_token": quote["quote_token"],
                "batch": 1,
                "provider": "runware",
                "model": "prunaai:p-video@0",
                "status": "unknown",
                "actual_cost_usd": "0",
                "regenerable": False,
                "video_path": "",
                "video_sha256": "",
                "segments": [],
            },
        )
        invocations = [json.loads(line)["argv"] for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(invocations, [["model", "pricing", "prunaai:p-video@0", "--format", "json"]])
        self.assertEqual(self.server.requests[-1], [{"taskType": "getTaskDetails", "taskUUID": quote["request_id"]}])
        self._assert_secret_absent(process)

    def test_insufficient_credits_archive_is_authoritative_absent(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        self.server.insufficient = True
        process = self._run(self._reconcile_request(quote))
        result = self._json_stdout(process)
        self.assertEqual(result["status"], "absent")
        self.assertEqual(result["actual_cost_usd"], "0")
        self.assertEqual(result["video_path"], "")
        self.assertEqual(result["segments"], [])

    def test_unusable_reconcile_video_returns_unknown(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json_stdout(quote_process)
        process = self._run(self._reconcile_request(quote), invalid_reconcile=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self._json_stdout(process)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["actual_cost_usd"], "0")
        self.assertEqual(result["video_path"], "")
        self.assertEqual(result["segments"], [])
        self._assert_secret_absent(process)

    def test_api_url_override_is_loopback_only_and_authorization_stays_local(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        local = self._run(self._reconcile_request(quote))
        self.assertEqual(self._json_stdout(local)["status"], "completed")
        self.assertEqual(self.server.headers[-1], f"Bearer {API_KEY}")
        before = len(self.server.requests)
        rejected = self._run(self._reconcile_request(quote), api_url=f"http://0.0.0.0:{self.server.server_port}/v1")
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual(self._json_stdout(rejected)["status"], "unknown")
        self.assertEqual(len(self.server.requests), before)
        self._assert_secret_absent(rejected)

    def test_redirect_is_not_followed_with_authorization(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        self.server.redirect = True
        self.server.redirect_target = f"http://127.0.0.1:{self.server.server_port}/v1"
        process = self._run(self._reconcile_request(quote), api_url=f"http://127.0.0.1:{self.server.server_port}/redirect")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self._json_stdout(process)["status"], "unknown")
        self.assertFalse(self.server.redirect_followed)
        self._assert_secret_absent(process)

    def test_task_details_rejects_wrong_outer_or_original_identity(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        for attribute, value in (
            ("outer_task_type", "videoInference"),
            ("outer_task_uuid", "wrong-task"),
            ("request_task_type", "imageInference"),
            ("request_model", "other:model@0"),
            ("request_task_uuid", "wrong-task"),
        ):
            with self.subTest(attribute=attribute):
                setattr(self.server, attribute, value)
                process = self._run(self._reconcile_request(quote))
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(self._json_stdout(process)["status"], "unknown")
                setattr(self.server, attribute, "" if attribute in {"outer_task_uuid", "request_task_uuid"} else {
                    "outer_task_type": "getTaskDetails", "request_task_type": "videoInference", "request_model": MODEL,
                }[attribute])

    def test_task_details_rejects_mixed_response_data_and_errors(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        self.server.mixed = True
        process = self._run(self._reconcile_request(quote))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self._json_stdout(process)["status"], "unknown")

    def test_insufficient_credits_requires_video_task_identity(self) -> None:
        quote = self._json_stdout(self._run(self._quote_request()))
        self.server.insufficient = True
        self.server.error_task_type = "imageInference"
        process = self._run(self._reconcile_request(quote))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self._json_stdout(process)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
