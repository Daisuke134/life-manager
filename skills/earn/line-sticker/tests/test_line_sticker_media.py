"""Contract tests for the fenced LINE sticker media pipeline."""

from __future__ import annotations

import errno
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import line_sticker_media as MODULE  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _executable(path: Path, source: str) -> Path:
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _model(path: Path) -> Path:
    return _executable(path, """
        #!/usr/bin/env python3
        import json
        from pathlib import Path
        import sys
        request = json.load(sys.stdin)
        count = Path(__file__).with_suffix('.count')
        count.write_text(str(int(count.read_text() or '0') + 1) if count.exists() else '1')
        if request['mode'] == 'plan':
            motions = []
            for batch in range(1, 7):
                for position in range(1, 11):
                    number = (batch - 1) * 10 + position
                    motions.append({'motion_id': f'motion-{number:02d}', 'batch': batch,
                      'position': position, 'intent': f'reaction {number}',
                      'action': f'clear action {number}', 'provider_prompt': f'animate {number}',
                      'duration_ms': 500})
            print(json.dumps({'version': 1, 'mode': 'plan', 'set_id': request['set_id'],
              'character_id': request['character_id'], 'character_anchors': ['blue ears'], 'motions': motions}))
            raise SystemExit
        value = json.loads(Path(request['selection_input_path']).read_text())
        candidates = value['candidates']
        valid = [item for item in candidates if not item['errors']]
        chosen = valid[:24]
        print(json.dumps({'version': 1, 'mode': 'select', 'cover_motion_id': chosen[0]['motion_id'],
          'inspected_candidate_hashes': [item['sha256'] for item in candidates],
          'selections': [{'position': i, 'motion_id': item['motion_id'], 'reason': 'observed motion'}
                         for i, item in enumerate(chosen, 1)]}))
    """)


def _provider(path: Path, template: Path) -> Path:
    return _executable(path, f"""
        #!/usr/bin/env python3
        import hashlib, json
        from pathlib import Path
        import subprocess, sys
        request = json.load(sys.stdin)
        log = Path(__file__).with_suffix('.jsonl')
        with log.open('a') as stream: stream.write(json.dumps(request) + '\\n')
        identity = {{'request_id': 'request-' + str(request['batch']), 'quote_token': 'token-' + str(request['batch']),
          'batch': request['batch'], 'provider': 'fixture-provider', 'model': 'fixture-model'}}
        if request['operation'] == 'quote':
            print(json.dumps({{**identity, 'quoted_cost_usd': '0.01', 'expires_at': '2999-01-01T00:00:00Z', 'regenerable': True}}))
            raise SystemExit
        if request['operation'] == 'reconcile':
            print(json.dumps({{**identity, 'acknowledged': 'unknown', 'video_path': '', 'video_sha256': '', 'segments': []}}))
            raise SystemExit
        if request['operation'] != 'generate' or any(request[key] != value for key, value in identity.items()):
            raise SystemExit(3)
        source = Path({str(template.parent)!r}) / ('source-' + str(request['batch']) + '.mp4')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', {str(template)!r}, '-vf', 'drawbox=x=' + str(request['batch']) + ':y=0:w=1:h=1:color=blue:t=fill', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-an', str(source)], check=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        segments = [{{'motion_id': motion['motion_id'], 'start_ms': (i - 1) * 500, 'end_ms': i * 500}}
                    for i, motion in enumerate(request['motions'], 1)]
        print(json.dumps({{**identity, 'acknowledged': True, 'video_path': str(source), 'video_sha256': digest,
          'segments': segments, 'regenerable': True, 'actual_cost_usd': '0.01'}}))
    """)


def _character(root: Path) -> Path:
    path = root / "character.png"
    path.write_bytes(b"original-character-rights-evidence")
    return path


def _rights_receipt(root: Path, character: Path) -> Path:
    path = root / "rights.json"
    path.write_text(json.dumps({"version": 1, "set_id": "set-1", "character_id": "char-1", "character_sha256": _sha256(character), "creation_source": "fixture-image-model", "rights": "original_ai_generated"}), encoding="utf-8")
    return path


def _video(root: Path) -> Path:
    path = root / "template.mp4"
    result = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "nullsrc=size=64x64:rate=10,geq=r='if(between(X,10+N,30+N)*between(Y,16,48),255,0)':g='if(between(X,10+N,30+N)*between(Y,16,48),0,255)':b=0",
        "-t", "5", "-pix_fmt", "yuv420p", "-an", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return path


class LineStickerMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="line-sticker-media-test-")
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.character = _character(self.root)
        self.rights_receipt = _rights_receipt(self.root, self.character)
        self.model = _model(self.root / "model.py")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _plan(self) -> None:
        MODULE.plan(self.character, [sys.executable, str(self.model)], self.work, "set-1", "char-1")

    def test_plan_prompt_gives_model_the_exact_top_level_schema(self) -> None:
        model = _executable(self.root / "schema-model.py", """
            #!/usr/bin/env python3
            import json, sys
            request = json.load(sys.stdin)
            prompt = request['creative_prompt']
            if not all(token in prompt for token in ('"version": 1', '"mode": "plan"', '"character_anchors"', '"motions"')):
                print(json.dumps({'set_id': request['set_id'], 'character_id': request['character_id'], 'candidates': []}))
                raise SystemExit
            motions = []
            for number in range(1, 61):
                motions.append({'motion_id': f'motion-{number:02d}', 'batch': (number - 1) // 10 + 1,
                  'position': (number - 1) % 10 + 1, 'intent': f'reaction {number}',
                  'action': f'action {number}', 'provider_prompt': f'animate {number}', 'duration_ms': 500})
            print(json.dumps({'version': 1, 'mode': 'plan', 'set_id': request['set_id'],
              'character_id': request['character_id'], 'character_anchors': ['blue ears'], 'motions': motions}))
        """)
        result = MODULE.plan(self.character, [sys.executable, str(model)], self.work, "set-1", "char-1")
        self.assertEqual(result["status"], "ready")

    def test_plan_requires_exact_safe_motion_ids_and_replays(self) -> None:
        self._plan()
        replay = MODULE.plan(self.character, [sys.executable, str(self.model)], self.work, "set-1", "char-1")
        self.assertEqual(replay["reason"], "replayed")
        self.assertEqual((self.root / "model.count").read_text(), "1")
        payload = json.loads((self.work / "plan.json").read_text())
        for unsafe_id in ("../../unsafe", "junk-01", "motion-1"):
            payload["motions"][0]["motion_id"] = unsafe_id
            with self.subTest(unsafe_id=unsafe_id), self.assertRaisesRegex(MODULE.MediaError, "motion_id_invalid"):
                MODULE._validate_plan_model({key: payload[key] for key in ("version", "mode", "set_id", "character_id", "character_anchors", "motions")}, set_id="set-1", character_id="char-1")
        (self.work / "plan-receipt.json").unlink()
        self._plan()
        self.assertEqual((self.root / "model.count").read_text(), "1")

    def test_plan_rejects_a_batch_longer_than_the_source_video(self) -> None:
        response = json.loads(subprocess.run(
            [sys.executable, str(self.model)],
            input=json.dumps({"mode": "plan", "set_id": "set-1", "character_id": "char-1"}),
            text=True, capture_output=True, check=True,
        ).stdout)
        for motion in response["motions"][:10]:
            motion["duration_ms"] = 1100
        with self.assertRaisesRegex(MODULE.MediaError, "duration_invalid"):
            MODULE._validate_plan_model(response, set_id="set-1", character_id="char-1")

    def test_rights_receipt_is_required_and_hash_binds_its_bytes(self) -> None:
        self._plan()
        bad = self.root / "bad-rights.json"
        bad.write_text(json.dumps({"version": 1, "set_id": "set-1", "character_id": "char-1", "character_sha256": _sha256(self.character), "creation_source": "fixture", "rights": "copied"}))
        with self.assertRaisesRegex(MODULE.MediaError, "rights_receipt_invalid"):
            MODULE._rights_receipt(bad, json.loads((self.work / "plan.json").read_text()))
        evidence = MODULE._rights_receipt(self.rights_receipt, json.loads((self.work / "plan.json").read_text()))
        self.rights_receipt.write_text(self.rights_receipt.read_text() + " ")
        self.assertEqual(evidence["receipt_sha256"], MODULE._rights_receipt(self.rights_receipt, json.loads((self.work / "plan.json").read_text()))["receipt_sha256"])

    def test_quote_reservation_precedes_generate_and_replay_has_no_provider_call(self) -> None:
        self._plan()
        provider = _provider(self.root / "provider.py", _video(self.root))
        first = MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "1.00", "ffmpeg", "ffprobe")
        second = MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "1.00", "ffmpeg", "ffprobe")
        calls = [json.loads(line) for line in (self.root / "provider.jsonl").read_text().splitlines()]
        self.assertEqual([call["operation"] for call in calls], ["quote", "generate"] * 6)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(second["effect"], 0)
        state = json.loads((self.work / "convert-state.json").read_text())
        self.assertEqual(state["batches"]["1"]["status"], "completed")
        self.assertFalse((self.work / "reservations").exists())

    def test_quote_over_cap_does_not_generate(self) -> None:
        self._plan()
        provider = _provider(self.root / "provider.py", _video(self.root))
        with self.assertRaisesRegex(MODULE.MediaError, "cost_exceeded"):
            MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "0.005", "ffmpeg", "ffprobe")
        calls = [json.loads(line) for line in (self.root / "provider.jsonl").read_text().splitlines()]
        self.assertEqual([call["operation"] for call in calls], ["quote"])

    def test_target_batch_stops_after_one_completed_batch(self) -> None:
        self._plan()
        provider = _provider(self.root / "provider.py", _video(self.root))
        result = MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "0.01", "ffmpeg", "ffprobe", target_batch=1)
        calls = [json.loads(line) for line in (self.root / "provider.jsonl").read_text().splitlines()]
        self.assertEqual([call["operation"] for call in calls], ["quote", "generate"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(json.loads((self.work / "convert-receipt.json").read_text())["candidate_count"], 10)
        self.assertEqual(set(json.loads((self.work / "convert-state.json").read_text())["batches"]), {"1"})

    def test_lowered_cap_keeps_reserved_batch_from_generating(self) -> None:
        self._plan()
        plan = json.loads((self.work / "plan.json").read_text())
        quote = {"request_id": "request-1", "quote_token": "token-1", "batch": 1, "provider": "fixture-provider", "model": "fixture-model", "quoted_cost_usd": "0.01", "expires_at": "2999-01-01T00:00:00Z", "regenerable": True}
        quote["reservation_key"] = MODULE._reservation_key(set_id="set-1", plan_hash=plan["plan_sha256"], batch=1, provider=quote["provider"], model=quote["model"], request_id=quote["request_id"], quote_token=quote["quote_token"], character_hash=plan["character_sha256"])
        state = {"version": 3, "plan_sha256": plan["plan_sha256"], "character_sha256": plan["character_sha256"], "batches": {"1": {"status": "reserved", "quote": quote}}}
        (self.work / "convert-state.json").write_text(json.dumps(state))
        provider = _executable(self.root / "must-not-run.py", "#!/usr/bin/env python3\nraise SystemExit(9)\n")
        with self.assertRaisesRegex(MODULE.MediaError, "cost_exceeded"):
            MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "0.005", "ffmpeg", "ffprobe")
        self.assertEqual(json.loads((self.work / "convert-state.json").read_text())["batches"]["1"]["status"], "reserved")

    def test_convert_state_is_the_only_batch_authority_and_expired_quotes_fail(self) -> None:
        state = MODULE._load_convert_state(self.work / "convert-state.json")
        self.assertEqual(set(state), {"version", "plan_sha256", "character_sha256", "batches"})
        expired = {"request_id": "r", "quote_token": "q", "batch": 1, "provider": "p", "model": "m", "quoted_cost_usd": "0.01", "expires_at": "2000-01-01T00:00:00Z", "regenerable": True}
        with self.assertRaisesRegex(MODULE.MediaError, "quote_expired"):
            MODULE._quote(expired, 1)

    def test_unknown_ack_reconciles_without_generate_retry(self) -> None:
        self._plan()
        provider = _executable(self.root / "unknown.py", """
            #!/usr/bin/env python3
            import json, sys
            request=json.load(sys.stdin); base={'request_id':'r','quote_token':'q','batch':request['batch'],'provider':'p','model':'m'}
            if request['operation']=='quote': print(json.dumps({**base,'quoted_cost_usd':'0.01','expires_at':'2999-01-01T00:00:00Z','regenerable':False}))
            elif request['operation']=='generate': print(json.dumps({**base,'acknowledged':'unknown','video_path':'','video_sha256':'','segments':[],'regenerable':False,'actual_cost_usd':'0.01'}))
            elif request['operation']=='reconcile': print(json.dumps({**base,'status':'unknown','actual_cost_usd':'0.01','regenerable':False,'video_path':'','video_sha256':'','segments':[]}))
        """)
        with self.assertRaisesRegex(MODULE.MediaError, "reconcile_required"):
            MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "1", "ffmpeg", "ffprobe")
        with self.assertRaisesRegex(MODULE.MediaError, "reconcile_unknown"):
            MODULE.reconcile(self.work / "convert-state.json", [sys.executable, str(provider)], 1)

    def test_process_group_output_cap_is_streamed(self) -> None:
        overflow = _executable(self.root / "overflow.py", """
            #!/usr/bin/env python3
            import sys, time
            sys.stdout.write('x' * (1024 * 1024 + 1)); sys.stdout.flush(); time.sleep(1)
        """)
        with self.assertRaisesRegex(MODULE.MediaError, "command_output_overflow"):
            MODULE._run_external([sys.executable, str(overflow)], cwd=self.work)

    def test_zero_reported_free_space_does_not_block_planning(self) -> None:
        usage = type("Usage", (), {"free": 0})()
        with mock.patch.object(MODULE.shutil, "disk_usage", return_value=usage) as disk_usage:
            self._plan()
        disk_usage.assert_not_called()
        self.assertEqual((self.root / "model.count").read_text(), "1")

    def test_atomic_write_preserves_checkpoint_on_enospc_and_retries(self) -> None:
        checkpoint = self.work / "checkpoint.json"
        checkpoint.write_bytes(b"prior")
        with mock.patch.object(MODULE.os, "replace", side_effect=OSError(errno.ENOSPC, "no space")) as replace:
            with self.assertRaisesRegex(MODULE.MediaError, "disk_full"):
                MODULE._atomic_bytes(checkpoint, b"next")
        replace.assert_called_once()
        self.assertEqual(checkpoint.read_bytes(), b"prior")

        MODULE._atomic_bytes(checkpoint, b"next")
        self.assertEqual(checkpoint.read_bytes(), b"next")

    def test_selection_requires_all_visual_hash_readback_and_changed_candidate_refreshes(self) -> None:
        self._plan()
        candidates = self.work / "candidates"; candidates.mkdir()
        for index in range(1, 61):
            path = candidates / f"motion-{index:02d}.png"; path.write_bytes(f"candidate-{index}".encode())
            (candidates / f"motion-{index:02d}.json").write_text(json.dumps({'version': 1, 'motion_id': f'motion-{index:02d}', 'path': str(path), 'candidate_sha256': _sha256(path), 'source_sha256': 'a'*64, 'segment': {'motion_id': f'motion-{index:02d}', 'start_ms': 0, 'end_ms': 500}, 'conversion_argv_sha256': 'b'*64, 'parsed': {}, 'validation_errors': [], 'first_frame_path': str(path), 'motion_preview_path': str(path)}))
        first = MODULE.select(self.work / "plan.json", candidates, [sys.executable, str(self.model)], self.work)
        (candidates / "motion-01.png").write_bytes(b"changed")
        second = MODULE.select(self.work / "plan.json", candidates, [sys.executable, str(self.model)], self.work)
        self.assertEqual(first["status"], "ready"); self.assertEqual(second["status"], "ready")
        self.assertEqual((self.root / "model.count").read_text(), "3")

    def test_select_model_receives_exact_machine_readable_schema_prompt(self) -> None:
        self._plan()
        candidates = self.work / "schema-candidates"; candidates.mkdir()
        for index in range(1, 61):
            path = candidates / f"motion-{index:02d}.png"; path.write_bytes(f"candidate-{(index - 1) % 12}".encode())
            (candidates / f"motion-{index:02d}.json").write_text(json.dumps({
                "version": 1, "motion_id": f"motion-{index:02d}", "path": str(path), "candidate_sha256": _sha256(path),
                "source_sha256": "a" * 64, "segment": {"motion_id": f"motion-{index:02d}", "start_ms": 0, "end_ms": 500},
                "conversion_argv_sha256": "b" * 64, "parsed": {}, "validation_errors": [],
                "first_frame_path": str(path), "motion_preview_path": str(path),
            }))
        model = _executable(self.root / "schema-select-model.py", """
            #!/usr/bin/env python3
            import json, sys
            from pathlib import Path
            request = json.load(sys.stdin)
            prompt = request['creative_prompt']
            try:
                select_prompt = prompt.split('## Mode: `select`', 1)[1]
                schema = json.loads(select_prompt.split('```json', 1)[1].split('```', 1)[0])
            except (IndexError, json.JSONDecodeError):
                schema = None
            expected = {
                'type': 'object', 'additionalProperties': False,
                'required': ['version', 'mode', 'cover_motion_id', 'inspected_candidate_hashes', 'selections'],
                'properties': {
                    'version': {'const': 1}, 'mode': {'const': 'select'},
                    'cover_motion_id': {'type': 'string', 'minLength': 1},
                    'inspected_candidate_hashes': {
                        'type': 'array', 'minItems': 60, 'maxItems': 60,
                        'items': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                    },
                    'selections': {
                        'type': 'array', 'minItems': 24, 'maxItems': 24,
                        'items': {
                            'type': 'object', 'additionalProperties': False,
                            'required': ['position', 'motion_id', 'reason'],
                            'properties': {
                                'position': {'type': 'integer', 'minimum': 1, 'maximum': 24},
                                'motion_id': {'type': 'string', 'minLength': 1},
                                'reason': {'type': 'string', 'minLength': 1},
                            },
                        },
                    },
                },
            }
            if schema != expected:
                print(json.dumps({'version': 1, 'mode': 'select', 'wrong_shape': True}))
                raise SystemExit
            payload = json.loads(Path(request['selection_input_path']).read_text())
            candidates = payload['candidates']
            chosen = candidates[:24]
            print(json.dumps({
                'version': 1, 'mode': 'select', 'cover_motion_id': chosen[0]['motion_id'],
                'inspected_candidate_hashes': [item['sha256'] for item in candidates],
                'selections': [{'position': position, 'motion_id': item['motion_id'], 'reason': 'observed evidence'}
                               for position, item in enumerate(chosen, 1)],
            }))
        """)
        result = MODULE.select(self.work / "plan.json", candidates, [sys.executable, str(model)], self.work)
        self.assertEqual(result["status"], "ready")

    def test_full_pipeline_writes_package_bound_generation(self) -> None:
        self._plan()
        provider = _provider(self.root / "provider.py", _video(self.root))
        MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "1.00", "ffmpeg", "ffprobe")
        state = json.loads((self.work / "convert-state.json").read_text())
        plan = json.loads((self.work / "plan.json").read_text())
        motions = MODULE._batch_motions(plan, 1)
        self.assertTrue(MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg"))
        forged = json.loads(json.dumps(state)); forged["batches"]["1"]["quote"]["batch"] = 2
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(forged, 1, motions, self.work, plan, "ffmpeg")
        forged = json.loads(json.dumps(state)); forged["batches"]["1"]["quote"]["reservation_key"] = "0" * 64
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(forged, 1, motions, self.work, plan, "ffmpeg")
        source = Path(state["batches"]["1"]["receipt"]["video_path"]); source_saved = source.read_bytes(); source.unlink()
        candidate = self.work / "candidates" / "motion-01.png"; saved = candidate.read_bytes(); candidate.unlink()
        with self.assertRaises(MODULE.MediaError):
            MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg")
        candidate.write_bytes(saved); source.write_bytes(source_saved)
        MODULE.select(self.work / "plan.json", self.work / "candidates", [sys.executable, str(self.model)], self.work)
        output = self.root / "package"
        result = MODULE.package(self.work / "selection.json", self.work, output, MODULE_ROOT / "official-policy.json", self.rights_receipt, "ffmpeg")
        provenance = json.loads((output / "provenance.json").read_text())
        self.assertEqual(result["status"], "ready")
        replay = MODULE.package(self.work / "selection.json", self.work, output, MODULE_ROOT / "official-policy.json", self.rights_receipt, "ffmpeg")
        self.assertEqual(replay["effect"], 0)
        self.assertEqual(set(provenance["generation"]), MODULE.GENERATION_KEYS)
        provenance["generation"]["plan_sha256"] = "0" * 64
        (output / "provenance.json").write_text(json.dumps(provenance))
        self.assertIn("provenance_invalid", MODULE.line_sticker.validate_package(output, MODULE_ROOT / "official-policy.json")["errors"])

    def test_completed_batch_source_and_candidate_fallback_are_exact(self) -> None:
        self._plan()
        provider = _provider(self.root / "provider.py", _video(self.root))
        MODULE.convert(self.work / "plan.json", [sys.executable, str(provider)], self.work, "1.00", "ffmpeg", "ffprobe")
        state = json.loads((self.work / "convert-state.json").read_text())
        plan = json.loads((self.work / "plan.json").read_text())
        motions = MODULE._batch_motions(plan, 1)
        source = Path(state["batches"]["1"]["receipt"]["video_path"])
        source_bytes = source.read_bytes()
        candidate_records = {
            path: path.read_bytes()
            for path in (self.work / "candidates").glob("motion-*.json")
        }

        for path in candidate_records:
            record = json.loads(path.read_text())
            record["source_sha256"] = "0" * 64
            path.write_text(json.dumps(record))
        forged = json.loads(json.dumps(state))
        forged["batches"]["1"]["receipt"]["video_sha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(forged, 1, motions, self.work, plan, "ffmpeg")
        for path, contents in candidate_records.items():
            path.write_bytes(contents)

        source.unlink()
        self.assertTrue(MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg"))

        def reject_candidate(mutator: object) -> None:
            path = self.work / "candidates" / "motion-01.json"
            record = json.loads(path.read_text())
            mutator(record)
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
                MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg")
            path.write_bytes(candidate_records[path])

        reject_candidate(lambda record: record.update({"validation_errors": ["candidate_png_invalid"]}))
        reject_candidate(lambda record: record.update({"segment": {"motion_id": "motion-01", "start_ms": 1, "end_ms": 500}}))

        candidate = self.work / "candidates" / "motion-01.png"
        candidate_saved = candidate.with_suffix(".saved")
        candidate.rename(candidate_saved)
        candidate.symlink_to(candidate_saved)
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg")

        candidate.unlink()
        candidate_saved.rename(candidate)

        source.write_bytes(source_bytes)
        source.unlink()
        source.symlink_to(candidate)
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg")
        source.unlink()
        source.mkdir()
        with self.assertRaisesRegex(MODULE.MediaError, "completed_receipt_invalid"):
            MODULE._completed_batch(state, 1, motions, self.work, plan, "ffmpeg")

    def test_alpha_hole_repair_keeps_exterior_transparent_and_fills_hole(self) -> None:
        width = height = 7
        raw = bytearray()
        for y in range(height):
            for x in range(width):
                if 2 <= x <= 4 and 2 <= y <= 4 and (x, y) != (3, 3):
                    raw.extend((120, 40, 80, 255))
                else:
                    raw.extend((0, 255, 0, 0))
        repaired = MODULE._repair_alpha_holes(bytes(raw), width, height)
        self.assertEqual(len(repaired), len(raw))
        for y in range(height):
            for x in range(width):
                pixel = repaired[(y * width + x) * 4 : (y * width + x + 1) * 4]
                if (x, y) == (3, 3):
                    self.assertEqual(pixel[3], 255)
                    self.assertNotEqual(tuple(pixel[:3]), (0, 255, 0))
                    self.assertEqual(tuple(pixel[:3]), (120, 40, 80))
                elif x in (0, width - 1) or y in (0, height - 1):
                    self.assertEqual(pixel[3], 0)

        with tempfile.TemporaryDirectory(prefix="alpha-hole-normalize-") as directory:
            path = Path(directory) / "hole.png"
            frames = []
            for index in range(5):
                frame = bytearray(raw)
                frame[(2 * width + 2) * 4] = 120 + index
                frames.append(bytes(frame))
            path.write_bytes(MODULE._encode_full_frame_apng(b"".join(frames), width=width, height=height, frames=5, duration_ms=Decimal("500")))
            MODULE._normalize_candidate_apng(path, ffmpeg="ffmpeg", duration_ms=Decimal("500"), cwd=Path(directory), width=width, height=height, fps=10)
            parsed = MODULE.line_sticker.parse_png(path)
            self.assertIsNone(MODULE.line_sticker._decode_and_check_alpha(path, parsed, "ffmpeg", set()))

    def test_alpha_hole_repair_keeps_deep_border_connected_transparency(self) -> None:
        width = height = 9
        raw = bytearray((0, 255, 0, 0) * (width * height))
        for x in range(2, 7):
            for y in (2, 6):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((120, 40, 80, 255))
        for y in range(2, 7):
            for x in (2, 6):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((120, 40, 80, 255))
        raw[(2 * width + 4) * 4 + 3] = 0
        repaired = MODULE._repair_alpha_holes(bytes(raw), width, height)
        for x, y in ((4, 3), (4, 4), (4, 5)):
            self.assertEqual(repaired[(y * width + x) * 4 + 3], 0)

    def test_alpha_hole_repair_propagates_multiple_non_green_seeds_deterministically(self) -> None:
        width = height = 7
        raw = bytearray((0, 255, 0, 0) * (width * height))
        red, blue = (220, 20, 20, 255), (20, 20, 220, 255)
        for x in range(1, 6):
            raw[(1 * width + x) * 4 : (1 * width + x + 1) * 4] = bytes(red)
            raw[(5 * width + x) * 4 : (5 * width + x + 1) * 4] = bytes(blue)
        for y in range(1, 6):
            raw[(y * width + 1) * 4 : (y * width + 2) * 4] = bytes(red)
            raw[(y * width + 5) * 4 : (y * width + 6) * 4] = bytes(blue)
        repaired = MODULE._repair_alpha_holes(bytes(raw), width, height)
        self.assertEqual(repaired, MODULE._repair_alpha_holes(bytes(raw), width, height))
        self.assertEqual(tuple(repaired[(2 * width + 3) * 4 : (2 * width + 3) * 4 + 3]), red[:3])
        self.assertEqual(tuple(repaired[(4 * width + 3) * 4 : (4 * width + 3) * 4 + 3]), blue[:3])
        self.assertNotEqual(
            tuple(repaired[(2 * width + 3) * 4 : (2 * width + 3) * 4 + 3]),
            tuple(repaired[(4 * width + 3) * 4 : (4 * width + 3) * 4 + 3]),
        )

    def test_alpha_hole_repair_fills_two_independent_holes_with_their_own_seeds(self) -> None:
        width, height = 11, 7
        raw = bytearray((0, 255, 0, 0) * (width * height))
        colors = ((2, (220, 20, 20)), (8, (20, 20, 220)))
        for center_x, color in colors:
            for x in range(center_x - 1, center_x + 2):
                for y in (1, 5):
                    raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((*color, 255))
            for y in range(1, 6):
                for x in (center_x - 1, center_x + 1):
                    raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((*color, 255))
        repaired = MODULE._repair_alpha_holes(bytes(raw), width, height)
        self.assertEqual(tuple(repaired[(3 * width + 2) * 4 : (3 * width + 2) * 4 + 3]), colors[0][1])
        self.assertEqual(tuple(repaired[(3 * width + 8) * 4 : (3 * width + 8) * 4 + 3]), colors[1][1])

    def test_alpha_hole_repair_reaches_valid_seed_outside_partial_and_green_rings(self) -> None:
        width = height = 9
        raw = bytearray((0, 255, 0, 0) * (width * height))
        partial = (200, 40, 80, 128)
        green = (100, 255, 0, 255)
        seed = (40, 80, 200, 255)
        for x in range(2, 7):
            for y in (2, 6):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(seed)
        for y in range(2, 7):
            for x in (2, 6):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(seed)
        for x in range(3, 6):
            for y in (3, 5):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(partial)
        for y in range(3, 6):
            for x in (3, 5):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(green)
        repaired = MODULE._repair_alpha_holes(bytes(raw), width, height)
        center = repaired[(4 * width + 4) * 4 : (4 * width + 4) * 4 + 4]
        self.assertEqual(tuple(center), seed)

    def test_alpha_hole_repair_rejects_partial_alpha_and_all_green_seeds(self) -> None:
        width = height = 5
        raw = bytearray((0, 255, 0, 0) * (width * height))
        for x in range(1, 4):
            for y in (1, 3):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((100, 255, 0, 255))
        for y in range(1, 4):
            for x in (1, 3):
                raw[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes((100, 255, 0, 255))
        raw[(1 * width + 2) * 4 : (1 * width + 2) * 4 + 4] = bytes((200, 40, 80, 128))
        with self.assertRaisesRegex(MODULE.MediaError, "alpha_hole_unrepairable"):
            MODULE._repair_alpha_holes(bytes(raw), width, height)


if __name__ == "__main__":
    unittest.main()
