"""CFO-only, app-scoped RevenueCat MRR readback."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from skills.cfo.adapters.capafy_mobile import MOBILE_PRODUCT_BINDINGS, MOBILE_PRODUCTS


ROOT = Path(__file__).resolve().parents[2]
BUSINESS_OUTCOMES = (
    ROOT / "skills/earn/marketing-engine/measure/business_outcomes.py"
)
_HELPERS = None


def _business_outcomes_helpers():
    global _HELPERS
    if _HELPERS is not None:
        return _HELPERS
    name = "life_manager_cfo_business_outcomes"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, BUSINESS_OUTCOMES)
        if spec is None or spec.loader is None:
            raise ImportError("business_outcomes_helpers_unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    _HELPERS = module
    return module


def _utc_text(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("readback_time_must_be_timezone_aware")
    return value.astimezone(dt.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _hash(value: Any, helpers) -> str:
    return helpers._json_hash(value)


def _source(status: str, reason: str | None, data: dict | None, helpers) -> dict:
    envelope = {"status": status, "reason": reason, "data": data}
    return {
        **envelope,
        "evidence_sha256": _hash(envelope, helpers),
    }


def _row(product: str, business_date: str, observed_at: str, source: dict) -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": f"{product}:{business_date}:cfo-revenuecat-mrr",
        "business_date": business_date,
        "observed_at": observed_at,
        "product_id": product,
        "sources": {"revenuecat": source},
    }


def _failed_row(
    product: str,
    app_id: str | None,
    business_date: str,
    observed_at: str,
    reason: str,
    query_scope: dict,
    helpers,
) -> dict:
    row = _row(
        product, business_date, observed_at,
        _source("unavailable", reason, None, helpers),
    )
    row["readback"] = {
        "provider": "revenuecat",
        "chart": "mrr",
        "app_id": app_id,
        "query_scope": query_scope,
        "scope_sha256": _hash(query_scope, helpers),
        "observed_at": observed_at,
    }
    return row


def fetch_current_mrr(
    *,
    project_id: str | None,
    api_key: str | None,
    product_bindings: dict[str, dict] = MOBILE_PRODUCT_BINDINGS,
    get: Callable | None = None,
    now: Callable[[], dt.datetime] | None = None,
) -> dict:
    """Fetch one exact MRR series per mobile app; errors stay unavailable."""
    helpers = _business_outcomes_helpers()
    current = now or (lambda: dt.datetime.now(dt.timezone.utc))
    started_at = _utc_text(current())
    end_date = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00")).date()
    end_text = end_date.isoformat()
    start_text = (end_date - dt.timedelta(days=27)).isoformat()
    def timed_result(rows, latest_observed_at=None):
        return {
            "rows": rows,
            "latest_observed_at": latest_observed_at,
            "started_at": started_at,
            "completed_at": _utc_text(current()),
        }
    product_names = tuple(MOBILE_PRODUCTS)
    if set(product_bindings) != set(product_names) or len(product_bindings) != 6:
        product_bindings = MOBILE_PRODUCT_BINDINGS

    project = str(project_id or "").strip()
    key = str(api_key or "").strip()
    project_path = urllib.parse.quote(project, safe="")
    base = f"https://api.revenuecat.com/v2/projects/{project_path}/charts/mrr"
    options_scope = {
        "project_id": project or None,
        "chart": "mrr",
        "endpoint": "options",
        "start_date": start_text,
        "end_date": end_text,
        "resolution": "0",
    }

    def unavailable_all(reason: str, observed_at: str, scope: dict) -> dict:
        rows = []
        for product in product_names:
            app_id = product_bindings[product].get("revenuecat_app_id")
            rows.append(_failed_row(
                product, app_id, end_text, observed_at, reason, scope, helpers,
            ))
        return timed_result(rows)

    if not project:
        return unavailable_all("project_id_missing", started_at, options_scope)
    if not key:
        scope = {**options_scope, "credential_status": "missing"}
        return unavailable_all("credential_missing", started_at, scope)

    request_json = get or helpers.http_json
    headers = {"Authorization": f"Bearer {key}"}
    options_url = f"{base}/options"
    try:
        options = request_json(options_url, headers)
    except Exception:
        return unavailable_all(
            "provider_query_failed", _utc_text(current()), options_scope,
        )
    if not isinstance(options, dict):
        return unavailable_all("scope_invalid", _utc_text(current()), options_scope)

    latest_observations: list[str] = []
    rows = []
    definition = dict(helpers.REVENUECAT_MRR_DEFINITION)
    for product in product_names:
        app_id = product_bindings[product].get("revenuecat_app_id")
        query_scope = {
            **options_scope,
            "app_id": app_id,
            "filters": None,
        }
        try:
            filters = helpers.revenuecat_app_filter(options, app_id)
            if (
                not isinstance(filters, list)
                or len(filters) != 1
                or filters[0].get("name") not in {"app_id", "app_config_id"}
                or filters[0].get("values") != [app_id]
            ):
                raise ValueError("app_filter_invalid")
        except Exception:
            rows.append(_failed_row(
                product, app_id, end_text, _utc_text(current()),
                "scope_invalid", query_scope, helpers,
            ))
            continue

        query_scope["filters"] = filters
        query = urllib.parse.urlencode({
            "start_date": start_text,
            "end_date": end_text,
            "resolution": "0",
            "filters": json.dumps(filters, separators=(",", ":")),
        })
        try:
            body = request_json(f"{base}?{query}", headers)
        except Exception:
            observed_at = _utc_text(current())
            rows.append(_failed_row(
                product, app_id, end_text, observed_at,
                "provider_query_failed", query_scope, helpers,
            ))
            continue

        observed_at = _utc_text(current())
        try:
            if not isinstance(body, dict):
                raise ValueError("chart_response_invalid")
            values = body.get("values")
            if isinstance(values, list) and any(
                isinstance(value, dict)
                and "incomplete" in value
                and type(value["incomplete"]) is not bool
                for value in values
            ):
                raise ValueError("chart_incomplete_flag_invalid")
            periods = body.get("periods") or []
            if not isinstance(periods, list):
                raise ValueError("chart_periods_invalid")
            normalized_periods = [
                dt.date.fromisoformat(helpers._normalize_mrr_period(period))
                for period in periods
            ]
            if normalized_periods != sorted(normalized_periods):
                raise ValueError("chart_period_order_invalid")
            expected_start = int(dt.datetime.combine(
                dt.date.fromisoformat(start_text), dt.time.min,
                tzinfo=dt.timezone.utc,
            ).timestamp())
            expected_end = int(dt.datetime.combine(
                dt.date.fromisoformat(end_text), dt.time.min,
                tzinfo=dt.timezone.utc,
            ).timestamp())
            if (
                type(body.get("start_date")) is not int
                or body["start_date"] != expected_start
                or type(body.get("end_date")) is not int
                or body["end_date"] != expected_end
                or body.get("resolution") != "day"
            ):
                rows.append(_failed_row(
                    product, app_id, end_text, observed_at,
                    "scope_invalid", query_scope, helpers,
                ))
                continue
            latest = helpers.latest_complete_chart_points(
                body, normalize_period_utc_date=True,
            )
            point = latest.get("MRR")
            if (
                not isinstance(point, dict)
                or point.get("incomplete") is not False
                or isinstance(point.get("value"), bool)
                or point.get("value") is None
            ):
                raise LookupError("mrr_point_unavailable")
            business_date = point.get("period")
            if not isinstance(business_date, str):
                raise ValueError("mrr_period_invalid")
            parsed_date = dt.date.fromisoformat(business_date)
            if parsed_date.isoformat() != business_date or not (
                start_text <= business_date <= end_text
            ):
                raise ValueError("mrr_period_out_of_scope")
            currency = body.get("yaxis_currency")
            if not isinstance(currency, str) or not currency:
                raise ValueError("currency_missing")
            chart = {
                "latest_complete": latest,
                "resolution": body.get("resolution"),
                "start_date": body.get("start_date"),
                "end_date": body.get("end_date"),
                "evidence_sha256": _hash(body, helpers),
            }
            data = {
                "app_id": app_id,
                "currency": currency,
                "revenue_definition": definition,
                "charts": {"mrr": chart},
                "readback": {
                    "provider": "revenuecat",
                    "chart": "mrr",
                    "observed_at": observed_at,
                    "query": query_scope,
                },
            }
            rows.append(_row(
                product, business_date, observed_at,
                _source("available", None, data, helpers),
            ))
            latest_observations.append(observed_at)
        except LookupError:
            rows.append(_failed_row(
                product, app_id, end_text, observed_at,
                "mrr_point_unavailable", query_scope, helpers,
            ))
        except (TypeError, ValueError, KeyError, OverflowError):
            rows.append(_failed_row(
                product, app_id, end_text, observed_at,
                "provider_response_invalid", query_scope, helpers,
            ))

    return timed_result(
        rows, max(latest_observations) if latest_observations else None,
    )
