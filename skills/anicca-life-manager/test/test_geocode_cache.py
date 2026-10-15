import io, json, os, sys, tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(REPO_ROOT / "skills/anicca-life-manager/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/_shared"))
import lateness_check as lc


def _response(payload):
    return mock.MagicMock(__enter__=lambda self: io.BytesIO(json.dumps(payload).encode()),
                          __exit__=lambda self, *a: False)


def run():
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(lc, "LOOP_STATE_DIR", Path(tmp)), \
            mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k"}, clear=False), \
            mock.patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = _response({"results": [{"geometry": {"location": {"lat": 35.1, "lng": 139.2}},
            "address_components": [{"long_name": "渋谷区", "types": ["locality"]}],
            "formatted_address": "x"}]})
        assert lc.geocode_place("東京都渋谷区1-1") == (35.1, 139.2)
        assert lc.geocode_place("東京都渋谷区1-1") == (35.1, 139.2)
        assert lc.reverse_geocode({"lat": 35.65812, "lon": 139.70171}) == "渋谷区"
        assert lc.reverse_geocode({"lat": 35.65818, "lon": 139.70179}) == "渋谷区"
        assert urlopen.call_count == 2, urlopen.call_count
    print("PASS")


run()
