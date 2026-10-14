from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .contracts import (
    ActionReceiptV1,
    ActionTargetV1,
    SessionHandleV1,
    SubmissionFenceLeaseV1,
    VisibleActionV1,
)
from .session import BrowserSession
from .direct_cdp import DirectCDPPage
from .submission_fence import SubmissionFence


_FINAL_SUBMIT = re.compile(
    r"^\s*(submit|submit application|送信|応募を送信)\s*$", re.IGNORECASE
)


class ActionExecutor:
    """Execute only fresh, unique, visible user-facing actions."""

    def __init__(self, session: BrowserSession, timeout_ms: int = 20_000) -> None:
        self._session = session
        self._timeout_ms = timeout_ms

    @staticmethod
    def _validate_https(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("navigation requires an absolute HTTPS URL")

    @staticmethod
    def _direct_target(target: ActionTargetV1) -> dict[str, object]:
        if not target.label.strip():
            raise ValueError("a non-empty user-facing label is required")
        return {
            "role": target.role,
            "label": target.label,
            "exact": target.exact,
            "stable_id": target.stable_id,
            "ordinal": target.ordinal,
        }

    async def _execute_direct(
        self, page: DirectCDPPage, action: VisibleActionV1
    ) -> None:
        if action.kind == "navigate":
            if action.url is None:
                raise ValueError("navigate requires url")
            self._validate_https(action.url)
            await page.goto(action.url)
            return
        if action.kind in {"click", "choose", "type", "select", "upload"}:
            if action.target is None:
                raise ValueError(f"{action.kind} requires target")
            if action.kind == "click" and _FINAL_SUBMIT.match(action.target.label):
                raise PermissionError("final Submit requires the SubmissionFence path")
            target = self._direct_target(action.target)
            if action.kind == "click":
                await page.click_target(target)
            elif action.kind == "choose":
                if action.opener is None:
                    raise ValueError("choose requires opener")
                opener = self._direct_target(action.opener)
                target_without_ephemeral_id = dict(target)
                target_without_ephemeral_id["stable_id"] = ""
                try:
                    await page.click_target(target)
                except RuntimeError:
                    try:
                        await page.click_target(target_without_ephemeral_id)
                    except RuntimeError:
                        await page.click_target(opener)
                        last_error: RuntimeError | None = None
                        for _ in range(15):
                            try:
                                await page.click_target(target)
                                break
                            except RuntimeError as error:
                                last_error = error
                                try:
                                    await page.click_target(target_without_ephemeral_id)
                                    break
                                except RuntimeError as fallback_error:
                                    last_error = fallback_error
                                    await asyncio.sleep(0.2)
                        else:
                            raise last_error or RuntimeError("provider option did not settle")
            elif action.kind == "type":
                if action.text is None:
                    raise ValueError("type requires text")
                await page.type_target(target, action.text)
            elif action.kind == "select":
                if action.text is None:
                    raise ValueError("select requires option label")
                await page.select_target(target, action.text)
            else:
                if action.file_path is None or not Path(action.file_path).is_file():
                    raise ValueError("upload requires an existing file")
                await page.upload_target(target, str(action.file_path))
            return
        if action.kind == "scroll":
            if type(action.delta_y) is not int or abs(action.delta_y) > 10_000:
                raise ValueError("scroll requires bounded delta_y")
            if action.target is None:
                await page.scroll(action.delta_y)
            else:
                if abs(action.delta_y) > 600:
                    raise ValueError("targeted scroll requires a delta up to 600")
                await page.scroll_target(
                    self._direct_target(action.target), action.delta_y
                )
            return
        if action.kind == "wait":
            if action.wait_ms is None or not 0 < action.wait_ms <= 10_000:
                raise ValueError("wait requires 1..10000 milliseconds")
            await page.wait_for_timeout(action.wait_ms)
            return
        raise ValueError(f"unsupported action kind: {action.kind}")

    async def _target(self, page, target: ActionTargetV1):
        if not target.label.strip():
            raise ValueError("a non-empty user-facing label is required")
        if target.stable_id:
            kind, separator, value = target.stable_id.partition(":")
            if not separator or kind not in {"automation", "id", "ref"} or not value:
                raise ValueError(
                    "stable_id must be automation:<value>, id:<value>, or ref:<value>"
                )
            attribute = {
                "automation": "data-automation-id",
                "id": "id",
                "ref": "data-anicca-ref",
            }[kind]
            locator = page.locator(f"[{attribute}={json.dumps(value)}]")
        else:
            locator = (
                page.get_by_role(target.role, name=target.label, exact=target.exact)
                if target.role
                else page.get_by_label(target.label, exact=target.exact)
            )
        async def resolve():
            visible = []
            for index in range(await locator.count()):
                candidate = locator.nth(index)
                if not await candidate.is_visible() or not await candidate.is_enabled():
                    continue
                if target.stable_id and not await candidate.evaluate(
                """(el, expected) => {
                  const own = el.getAttribute('aria-label') || el.getAttribute('title') || '';
                  const linked = el.labels && el.labels.length
                    ? Array.from(el.labels).map(x => x.innerText).join(' ') : '';
                  const actual = (own || linked || el.getAttribute('placeholder') || el.innerText || '').trim();
                  const variants = [actual];
                  variants.push(actual.replace(/\\s+(?:not checked|checked)$/i, ''));
                  if (el.hasAttribute('aria-checked')) {
                    variants.push(`${actual} ${el.getAttribute('aria-checked') === 'true' ? 'checked' : 'not checked'}`);
                  }
                  return expected.exact
                    ? variants.includes(expected.label)
                    : variants.some(value => value.includes(expected.label));
                }""",
                {"label": target.label, "exact": target.exact},
                ):
                    continue
                visible.append(candidate)
            return visible

        visible = await resolve()
        if target.ordinal is not None:
            if target.ordinal < 1 or target.ordinal > len(visible):
                raise RuntimeError("action target ordinal is outside the visible controls")
            return visible[target.ordinal - 1]
        if len(visible) != 1:
            raise RuntimeError(
                "action target must resolve to exactly one visible enabled control"
            )
        return visible[0]

    async def execute(
        self, handle: SessionHandleV1, action: VisibleActionV1
    ) -> ActionReceiptV1:
        page = self._session.page(handle)
        before_url = page.url
        target = None
        if isinstance(page, DirectCDPPage):
            await self._execute_direct(page, action)
        elif action.kind == "navigate":
            if action.url is None:
                raise ValueError("navigate requires url")
            self._validate_https(action.url)
            await page.goto(action.url, wait_until="commit", timeout=self._timeout_ms)
        elif action.kind in {"click", "choose", "type", "select", "upload"}:
            if action.target is None:
                raise ValueError(f"{action.kind} requires target")
            if action.kind == "click" and _FINAL_SUBMIT.match(action.target.label):
                raise PermissionError("final Submit requires the SubmissionFence path")
            if action.kind == "choose":
                if action.opener is None:
                    raise ValueError("choose requires opener")
                try:
                    target = await self._target(page, action.target)
                except RuntimeError:
                    try:
                        opener = await self._target(page, action.opener)
                    except RuntimeError:
                        opener = await self._target(
                            page,
                            ActionTargetV1(
                                role=action.opener.role,
                                label=action.opener.label,
                                exact=action.opener.exact,
                            ),
                        )
                    await opener.click(timeout=self._timeout_ms)
                    try:
                        target = await self._target(page, action.target)
                    except RuntimeError:
                        raise RuntimeError(
                            "option is not present in the fresh observation; observe the "
                            "opened control and choose its new ref in the next model step"
                        )
            else:
                target = await self._target(page, action.target)
            if action.kind in {"click", "choose"}:
                is_checkable = await target.evaluate(
                    "el => el.tagName === 'INPUT' && ['radio', 'checkbox'].includes(el.type)"
                )
                if action.kind == "click" and is_checkable:
                    await target.check(timeout=self._timeout_ms)
                else:
                    await target.click(timeout=self._timeout_ms)
            elif action.kind == "type":
                if action.text is None:
                    raise ValueError("type requires text")
                await target.fill(action.text, timeout=self._timeout_ms)
            elif action.kind == "select":
                if action.text is None:
                    raise ValueError("select requires option label")
                await target.select_option(label=action.text, timeout=self._timeout_ms)
            else:
                if action.file_path is None or not Path(action.file_path).is_file():
                    raise ValueError("upload requires an existing file")
                is_file_input = await target.evaluate(
                    "el => el.tagName === 'INPUT' && el.type === 'file'"
                )
                if is_file_input:
                    await target.set_input_files(
                        str(action.file_path), timeout=self._timeout_ms
                    )
                else:
                    async with page.expect_file_chooser(
                        timeout=self._timeout_ms
                    ) as chooser_info:
                        await target.click(timeout=self._timeout_ms)
                    chooser = await chooser_info.value
                    await chooser.set_files(str(action.file_path))
        elif action.kind == "scroll":
            if type(action.delta_y) is not int or abs(action.delta_y) > 10_000:
                raise ValueError("scroll requires bounded delta_y")
            if action.target is None:
                await page.mouse.wheel(0, action.delta_y)
            else:
                if abs(action.delta_y) > 600:
                    raise ValueError("targeted scroll requires a delta up to 600")
                target = await self._target(page, action.target)
                box = await target.bounding_box()
                if not box:
                    raise RuntimeError("scroll anchor is no longer visible")
                await page.mouse.move(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
                await page.mouse.wheel(0, action.delta_y)
                await page.wait_for_timeout(350)
        elif action.kind == "wait":
            if action.wait_ms is None or not 0 < action.wait_ms <= 10_000:
                raise ValueError("wait requires 1..10000 milliseconds")
            await page.wait_for_timeout(action.wait_ms)
        else:
            raise ValueError(f"unsupported action kind: {action.kind}")

        safe = {
            "kind": action.kind,
            "target_role": action.target.role if action.target else None,
            "target_label": action.target.label if action.target else None,
            "target_stable_id": action.target.stable_id if action.target else None,
            "before_url": before_url,
            "after_url": page.url,
        }
        receipt_sha = hashlib.sha256(
            json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return ActionReceiptV1(1, receipt_sha256=receipt_sha, **safe)

    async def execute_final(
        self,
        handle: SessionHandleV1,
        action: VisibleActionV1,
        fence: SubmissionFence,
        lease: SubmissionFenceLeaseV1,
        observation_sha256: str,
    ) -> ActionReceiptV1:
        """Consume one fresh fence and click one visible final Submit exactly once."""
        if (
            action.kind != "click"
            or action.target is None
            or not _FINAL_SUBMIT.match(action.target.label)
        ):
            raise ValueError("final action must be the visible Submit click")
        page = self._session.page(handle)
        before_url = page.url
        fence_receipt = fence.consume(lease, observation_sha256)
        click_error_type = None
        try:
            if isinstance(page, DirectCDPPage):
                await page.click_target(self._direct_target(action.target))
            else:
                target = await self._target(page, action.target)
                await target.click(timeout=self._timeout_ms)
        except Exception as error:
            # Once the fence is consumed the click may have reached the provider.
            # Return an opaque receipt so the caller observes and classifies the
            # rendered result exactly once instead of retrying an ambiguous submit.
            click_error_type = type(error).__name__
        safe = {
            "kind": action.kind,
            "target_role": action.target.role,
            "target_label": action.target.label,
            "target_stable_id": action.target.stable_id,
            "before_url": before_url,
            "after_url": page.url,
            "fence_receipt_sha256": fence_receipt,
            "click_error_type": click_error_type,
        }
        receipt_sha = hashlib.sha256(
            json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        safe.pop("click_error_type")
        return ActionReceiptV1(1, receipt_sha256=receipt_sha, **safe)
