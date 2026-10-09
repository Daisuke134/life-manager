"""Read the one scoped Treg identity from the private credentials SSOT."""

from __future__ import annotations

import json
import stat
from pathlib import Path


TREG_AGENT_CREDENTIAL_SERVICE = "treg_agent:life-manager-product-growth"


def load_treg_agent_token(credentials_path: Path | None = None) -> str | None:
    path = credentials_path or (
        Path.home() / ".local" / "share" / "anicca" / "credentials.json"
    )
    try:
        file_stat = path.lstat()
        parent_stat = path.parent.lstat()
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or not stat.S_ISDIR(parent_stat.st_mode)
            or stat.S_IMODE(parent_stat.st_mode) != 0o700
        ):
            raise ValueError("Treg credential SSOT permissions are invalid")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Treg credential SSOT is unavailable or invalid") from error
    credentials = data.get("credentials") if isinstance(data, dict) else None
    if not isinstance(credentials, list):
        raise ValueError("Treg credential SSOT has an invalid structure")
    matches = [
        row for row in credentials
        if isinstance(row, dict) and row.get("service") == TREG_AGENT_CREDENTIAL_SERVICE
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Treg agent credential is ambiguous")
    token = matches[0].get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Treg agent credential is empty")
    return token.strip()
