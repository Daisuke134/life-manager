import os
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "drive_checkpoint2.py").read_text()


def test_cp2_defaults_to_cheap_hosted_model():
    match = re.search(r'MODEL\s*=\s*os\.environ\.get\("CAPAFY_HOSTED_MODEL_ID",\s*"([^"]+)"\)', SRC)
    assert match and match.group(1) == "deepseek/deepseek-v4.1-flash"
