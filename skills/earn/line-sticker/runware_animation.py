#!/usr/bin/env python3
"""Runware P-Video adapter for the LINE sticker media command protocol."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import uuid


PROVIDER = "runware"
MODEL = "prunaai:p-video@0"
UNIT_PRICE = Decimal("0.005")
MOTION_COUNT = 10
MEDIA_UUID_ENV = "LINE_STICKER_RUNWARE_MEDIA_UUID"
BIN_ENV = "LINE_STICKER_RUNWARE_BIN"
API_URL_ENV = "LINE_STICKER_RUNWARE_API_URL"
DEFAULT_API_URL = "https://api.runware.ai/v1"


class AdapterError(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _env() -> tuple[str, str, str]:
    key = os.environ.get("RUNWARE_API_KEY", "")
    media_uuid = os.environ.get(MEDIA_UUID_ENV, "")
    binary = os.environ.get(BIN_ENV, "runware")
    try:
        media_uuid = str(uuid.UUID(media_uuid))
    except ValueError as exc:
        raise AdapterError("configuration_error") from exc
    if not key or not binary:
        raise AdapterError("configuration_error")
    return key, media_uuid, binary


def _hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _motions(value: object, batch: int) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != MOTION_COUNT:
        raise AdapterError("motions_invalid")
    result: list[dict[str, object]] = []
    keys = {"motion_id", "batch", "position", "intent", "action", "provider_prompt", "duration_ms"}
    for index, motion in enumerate(value, 1):
        expected_id = f"motion-{(batch - 1) * 10 + index:02d}"
        if not isinstance(motion, dict) or set(motion) != keys:
            raise AdapterError("motions_invalid")
        if motion.get("motion_id") != expected_id or motion.get("batch") != batch:
            raise AdapterError("motions_invalid")
        if motion.get("position") != index or motion.get("duration_ms") != 1000:
            raise AdapterError("motions_invalid")
        if any(not isinstance(motion.get(field), str) or not str(motion[field]).strip() for field in ("intent", "action", "provider_prompt")):
            raise AdapterError("motions_invalid")
        result.append(motion)
    if len({str(motion["motion_id"]) for motion in result}) != MOTION_COUNT:
        raise AdapterError("motions_invalid")
    return result


def _expiry() -> str:
    now = datetime.now(timezone.utc)
    expiry = datetime.combine(now.date() + timedelta(days=2), datetime.min.time(), timezone.utc)
    return expiry.isoformat().replace("+00:00", "Z")


def _quote_payload(request: dict[str, object], media_uuid: str, price: Decimal) -> dict[str, object]:
    if request.get("version") != 1 or request.get("operation") != "quote":
        raise AdapterError("request_invalid")
    if not all(isinstance(request.get(key), str) and str(request[key]).strip() for key in ("set_id", "character_id")):
        raise AdapterError("request_invalid")
    if not _hash(request.get("character_sha256")) or not _hash(request.get("plan_sha256")):
        raise AdapterError("request_invalid")
    batch = request.get("batch")
    if type(batch) is not int or not 1 <= batch <= 6:
        raise AdapterError("request_invalid")
    motions = _motions(request.get("motions"), batch)
    identity = {
        "version": 1,
        "provider": PROVIDER,
        "model": MODEL,
        "set_id": request["set_id"],
        "character_id": request["character_id"],
        "character_sha256": request["character_sha256"],
        "plan_sha256": request["plan_sha256"],
        "batch": batch,
        "media_uuid": media_uuid,
        "motion_ids": [motion["motion_id"] for motion in motions],
        "quoted_cost_usd": format(price, "f"),
        "expires_at": _expiry(),
    }
    identity["request_id"] = str(uuid.UUID(bytes=hashlib.sha256(_canonical(identity)).digest()[:16], version=4))
    return identity


def _token(payload: dict[str, object], key: str) -> str:
    encoded = base64.urlsafe_b64encode(_canonical(payload)).rstrip(b"=")
    signature = hmac.new(key.encode(), encoded, hashlib.sha256).hexdigest().encode()
    return (encoded + b"." + signature).decode()


def _decode(token: object, key: str) -> dict[str, object]:
    if not isinstance(token, str):
        raise AdapterError("quote_token_invalid")
    try:
        encoded, signature = token.encode().rsplit(b".", 1)
        expected = hmac.new(key.encode(), encoded, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(signature, expected):
            raise AdapterError("quote_token_invalid")
        padded = encoded + b"=" * (-len(encoded) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AdapterError("quote_token_invalid") from exc
    if not isinstance(value, dict):
        raise AdapterError("quote_token_invalid")
    return value


def _segments(payload: dict[str, object]) -> list[dict[str, object]]:
    ids = payload.get("motion_ids")
    if not isinstance(ids, list) or len(ids) != MOTION_COUNT:
        raise AdapterError("quote_token_invalid")
    return [
        {"motion_id": motion_id, "start_ms": index * 1000, "end_ms": (index + 1) * 1000}
        for index, motion_id in enumerate(ids)
    ]


def _verify_token(request: dict[str, object], key: str, media_uuid: str, *, enforce_expiry: bool = True) -> dict[str, object]:
    payload = _decode(request.get("quote_token"), key)
    if payload.get("provider") != PROVIDER or payload.get("model") != MODEL or payload.get("media_uuid") != media_uuid:
        raise AdapterError("provider_identity_mismatch")
    for field in ("request_id", "batch", "provider", "model"):
        if request.get(field) != payload.get(field):
            raise AdapterError("provider_identity_mismatch")
    try:
        expires = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise AdapterError("quote_token_invalid") from exc
    if enforce_expiry and expires <= datetime.now(timezone.utc):
        raise AdapterError("quote_expired")
    return payload


def _official_price(binary: str) -> Decimal:
    value = _run(binary, ["model", "pricing", MODEL, "--format", "json"])
    if value.get("air") != MODEL or value.get("status") != "live" or not isinstance(value.get("pricingExamples"), list):
        raise AdapterError("pricing_invalid")
    matches = [item for item in value["pricingExamples"] if isinstance(item, dict) and item.get("configuration") == "720p · 1s · DRAFT MODE"]
    if len(matches) != 1 or not isinstance(matches[0].get("price"), str):
        raise AdapterError("pricing_invalid")
    try:
        unit = Decimal(str(matches[0]["price"]).removeprefix("$"))
    except InvalidOperation as exc:
        raise AdapterError("pricing_invalid") from exc
    if unit != UNIT_PRICE:
        raise AdapterError("pricing_changed")
    return unit * MOTION_COUNT


def quote(request: dict[str, object], key: str, media_uuid: str, binary: str) -> dict[str, object]:
    payload = _quote_payload(request, media_uuid, UNIT_PRICE * MOTION_COUNT)
    price = _official_price(binary)
    if Decimal(str(payload["quoted_cost_usd"])) != price:
        raise AdapterError("pricing_changed")
    return {
        "request_id": payload["request_id"],
        "quote_token": _token(payload, key),
        "batch": payload["batch"],
        "provider": PROVIDER,
        "model": MODEL,
        "quoted_cost_usd": format(price.quantize(Decimal("0.01")), "f"),
        "expires_at": payload["expires_at"],
        "regenerable": False,
    }


def _prompt(motions: list[dict[str, object]]) -> str:
    timeline = " ".join(
        f"{index - 1}-{index}s: {str(motion['provider_prompt']).strip()}"
        for index, motion in enumerate(motions, 1)
    )
    return (
        "Use the supplied first-frame character identity. Keep one centered character on a solid #00FF00 "
        "background with no text, no logo, no cuts, and no extra objects. " + timeline
    )


def _run(binary: str, arguments: list[str]) -> dict[str, object]:
    process = subprocess.run([binary, *arguments], text=True, capture_output=True, timeout=900)
    if process.returncode:
        raise AdapterError("provider_unknown")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError("provider_unknown") from exc
    if not isinstance(value, dict):
        raise AdapterError("provider_unknown")
    return value


def _materialize(value: dict[str, object], payload: dict[str, object]) -> tuple[str, str, str]:
    if value.get("taskUUID") != payload.get("request_id") or not isinstance(value.get("videoURL"), str):
        raise AdapterError("provider_unknown")
    try:
        cost = Decimal(str(value.get("cost")))
    except InvalidOperation as exc:
        raise AdapterError("provider_unknown") from exc
    try:
        quoted = Decimal(str(payload["quoted_cost_usd"]))
    except (KeyError, InvalidOperation) as exc:
        raise AdapterError("quote_token_invalid") from exc
    if cost < 0 or cost > quoted:
        raise AdapterError("provider_unknown")
    destination = (Path.cwd() / f"source-batch-{payload['batch']}.mp4").resolve()
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as stream:
            temporary = stream.name
            source = Path(str(value["videoURL"]))
            if source.is_absolute() and source.is_file():
                with source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, stream)
            else:
                parsed = urlparse(str(value["videoURL"]))
                if parsed.scheme != "https":
                    raise AdapterError("provider_unknown")
                with urlopen(str(value["videoURL"]), timeout=300) as incoming:
                    shutil.copyfileobj(incoming, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    except (OSError, ValueError) as exc:
        raise AdapterError("provider_unknown") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return str(destination), _hash_file(destination), format(cost, "f")


def _receipt(request: dict[str, object], payload: dict[str, object], value: dict[str, object], *, reconcile: bool) -> dict[str, object]:
    video_path, video_hash, cost = _materialize(value, payload)
    result = {
        "request_id": payload["request_id"],
        "quote_token": request["quote_token"],
        "batch": payload["batch"],
        "provider": PROVIDER,
        "model": MODEL,
        "actual_cost_usd": cost,
        "regenerable": False,
        "video_path": video_path,
        "video_sha256": video_hash,
        "segments": _segments(payload),
    }
    if reconcile:
        result["status"] = "completed"
    else:
        result["acknowledged"] = True
    return result


def generate(request: dict[str, object], key: str, media_uuid: str, binary: str) -> dict[str, object]:
    if request.get("version") != 1 or request.get("operation") != "generate":
        raise AdapterError("request_invalid")
    payload = _verify_token(request, key, media_uuid)
    for field in ("set_id", "character_id", "character_sha256", "plan_sha256"):
        if request.get(field) != payload.get(field):
            raise AdapterError("provider_identity_mismatch")
    motions = _motions(request.get("motions"), int(payload["batch"]))
    if [motion["motion_id"] for motion in motions] != payload.get("motion_ids"):
        raise AdapterError("provider_identity_mismatch")
    path = Path(str(request.get("character_path", "")))
    if not path.is_file() or _hash_file(path) != payload.get("character_sha256"):
        raise AdapterError("character_hash_mismatch")
    try:
        cap = Decimal(str(request.get("remaining_cap_usd")))
    except InvalidOperation as exc:
        raise AdapterError("cost_invalid") from exc
    price = Decimal(str(payload["quoted_cost_usd"]))
    if cap < price:
        raise AdapterError("cost_exceeded")
    prompt = _prompt(motions)
    arguments = [
        "run", MODEL, "--task-type", "videoInference", "--delivery-method", "async",
        "--format", "json", "--no-download", "--validate", f"positivePrompt={prompt}",
        "resolution=720p", "duration=10", "fps=24", f"inputs.frameImages.0={media_uuid}",
        "settings.audio=false", "settings.draft=true", "settings.promptUpsampling=false",
        "includeCost=true", "numberResults=1", "outputFormat=MP4", f"taskUUID={payload['request_id']}",
    ]
    return _receipt(request, payload, _run(binary, arguments), reconcile=False)


def _unknown(request: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    return {
        "request_id": payload["request_id"], "quote_token": request["quote_token"],
        "batch": payload["batch"], "provider": PROVIDER, "model": MODEL, "status": "unknown",
        "actual_cost_usd": "0", "regenerable": False, "video_path": "", "video_sha256": "", "segments": [],
    }


def _absent(request: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    return {**_unknown(request, payload), "status": "absent"}


def _api_url() -> str:
    value = os.environ.get(API_URL_ENV)
    if value is None:
        return DEFAULT_API_URL
    try:
        parsed = urlparse(value)
        host = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise AdapterError("provider_unknown") from exc
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AdapterError("provider_unknown")
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback:
        raise AdapterError("provider_unknown")
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _task_details(key: str, task_id: str) -> dict[str, object]:
    body = _canonical([{"taskType": "getTaskDetails", "taskUUID": task_id}])
    request = Request(
        _api_url(),
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=30) as response:
            value = json.loads(response.read())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AdapterError("provider_unknown") from exc
    if not isinstance(value, dict) or "errors" in value or not isinstance(value.get("data"), list) or len(value["data"]) != 1:
        raise AdapterError("provider_unknown")
    details = value["data"][0]
    original = details.get("request") if isinstance(details, dict) else None
    if (
        not isinstance(details, dict)
        or details.get("taskType") != "getTaskDetails"
        or details.get("taskUUID") != task_id
        or not isinstance(original, list)
        or len(original) != 1
        or not isinstance(original[0], dict)
        or original[0].get("taskType") != "videoInference"
        or original[0].get("model") != MODEL
        or original[0].get("taskUUID") != task_id
        or not isinstance(details.get("response"), dict)
    ):
        raise AdapterError("provider_unknown")
    response = details["response"]
    has_data, has_errors = "data" in response, "errors" in response
    if has_data == has_errors or not isinstance(response.get("data" if has_data else "errors"), list):
        raise AdapterError("provider_unknown")
    return response


def reconcile(request: dict[str, object], key: str, media_uuid: str, binary: str) -> dict[str, object]:
    if request.get("version") != 1 or request.get("operation") != "reconcile":
        raise AdapterError("request_invalid")
    payload = _verify_token(request, key, media_uuid, enforce_expiry=False)
    try:
        archive = _task_details(key, str(payload["request_id"]))
        errors = archive.get("errors")
        if isinstance(errors, list) and len(errors) == 1 and isinstance(errors[0], dict) and errors[0].get("code") == "videoInferenceInsufficientCredits" and errors[0].get("taskType") == "videoInference" and errors[0].get("taskUUID") == payload["request_id"]:
            return _absent(request, payload)
        data = archive.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or data[0].get("taskType") != "videoInference" or data[0].get("taskUUID") != payload["request_id"] or data[0].get("status") != "success":
            return _unknown(request, payload)
        return _receipt(request, payload, data[0], reconcile=True)
    except AdapterError:
        return _unknown(request, payload)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise AdapterError("request_invalid")
        key, media_uuid, binary = _env()
        operation = request.get("operation")
        if operation == "quote":
            result = quote(request, key, media_uuid, binary)
        elif operation == "generate":
            result = generate(request, key, media_uuid, binary)
        elif operation == "reconcile":
            result = reconcile(request, key, media_uuid, binary)
        else:
            raise AdapterError("request_invalid")
        code = 0
    except (AdapterError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        result, code = {"error": "adapter_error"}, 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
