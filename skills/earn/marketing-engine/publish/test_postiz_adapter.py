import pathlib
import sys
import datetime as dt
import urllib.parse

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intent_store import IntentStore, stable_id
from postiz_adapter import HttpPostizClient, PostizAdapter, unique_remote_match
from test_intent_store import fixture_intent


class FakePostiz:
    def __init__(self, *, upload_result=None, create_result=None, promote_result=None,
                 upload_error=None, create_error=None, integrations=None):
        self.upload_result = upload_result or {
            "id": "media-123", "name": "approved.mp4",
            "path": "https://uploads.postiz.com/approved.mp4",
            "organizationId": "org-123", "createdAt": "2026-08-02T00:00:00Z",
            "updatedAt": "2026-08-02T00:00:00Z",
        }
        self.create_result = create_result or [{
            "postId": "post-123", "integration": "cmn8y95rg02d2qx0y09bbk5pb"
        }]
        self.promote_result = promote_result or {"id": "post-123", "state": "QUEUE"}
        self.upload_error = upload_error
        self.create_error = create_error
        self.integrations = integrations or [{
            "id": "cmn8y95rg02d2qx0y09bbk5pb", "identifier": "instagram-standalone",
            "profile": "anicca.en", "disabled": False}]
        self.integration_calls = 0
        self.upload_calls = 0
        self.create_calls = 0
        self.promote_calls = 0
        self.last_create_payload = None

    def upload_file(self, path):
        self.upload_calls += 1
        if self.upload_error:
            raise self.upload_error
        return self.upload_result

    def create_draft(self, payload):
        self.create_calls += 1
        self.last_create_payload = payload
        if self.create_error:
            raise self.create_error
        return self.create_result

    def promote(self, post_id):
        self.promote_calls += 1
        return self.promote_result

    def list_integrations(self):
        self.integration_calls += 1
        return self.integrations


def setup(tmp_path):
    store = IntentStore(tmp_path / "jobs.sqlite3")
    intent = store.register(fixture_intent(tmp_path))["intent"]
    lease = store.acquire(intent["publish_key"], owner="worker", now="2026-08-01T00:00:00Z",
                          ttl_seconds=300)
    return store, intent, lease


def test_list_posts_rejects_malformed_response_envelope():
    client = HttpPostizClient("test-key")
    client._json = lambda *_args: {"items": []}
    start = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)

    with pytest.raises(ValueError, match="Postiz posts response malformed"):
        client.list_posts(start, start + dt.timedelta(hours=1))


def test_list_posts_uses_documented_date_filters_without_unsupported_limit():
    client = HttpPostizClient("test-key")
    request = {}

    def read(_method, path):
        request["path"] = path
        return {"posts": []}

    client._json = read
    start = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)

    assert client.list_posts(start, start + dt.timedelta(hours=1)) == []
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request["path"]).query)
    assert set(query) == {"startDate", "endDate"}


def test_upload_create_draft_and_promote_each_call_provider_once(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz()
    adapter = PostizAdapter(store, client)
    uploaded = adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                                    now="2026-08-01T00:00:01Z")
    upload_replay = adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                                         now="2026-08-01T00:00:02Z")
    assert uploaded["state"] == upload_replay["state"] == "accepted"
    assert client.upload_calls == 1
    first = adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                                 now="2026-08-01T00:00:03Z")
    second = adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                                  now="2026-08-01T00:00:04Z")
    assert first["state"] == second["state"] == "accepted"
    assert client.create_calls == 1
    assert client.last_create_payload["posts"][0]["value"][0]["image"] == [{
        "id": "media-123", "path": "https://uploads.postiz.com/approved.mp4"
    }]
    assert client.last_create_payload["posts"][0]["settings"] == intent["provider_settings"]
    adapter.promote(intent["publish_key"], "worker", lease["fence"],
                    now="2026-08-01T00:00:05Z")
    adapter.promote(intent["publish_key"], "worker", lease["fence"],
                    now="2026-08-01T00:00:06Z")
    assert client.promote_calls == 1


def test_create_draft_before_media_upload_fails_closed(tmp_path):
    store, intent, lease = setup(tmp_path)
    adapter = PostizAdapter(store, FakePostiz())
    with pytest.raises(ValueError, match="cannot create draft without stored media receipt"):
        adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                             now="2026-08-01T00:00:01Z")


def test_upload_timeout_is_uncertain_and_never_retried(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz(upload_error=TimeoutError("upload response lost"))
    adapter = PostizAdapter(store, client)
    first = adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                                 now="2026-08-01T00:00:01Z")
    second = adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                                  now="2026-08-01T00:00:02Z")
    assert first["state"] == second["state"] == "uncertain"
    assert client.upload_calls == 1


def test_timeout_after_dispatch_is_uncertain_and_not_retried(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz(create_error=TimeoutError("network timeout"))
    adapter = PostizAdapter(store, client)
    adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                         now="2026-08-01T00:00:00Z")
    result = adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                                  now="2026-08-01T00:00:01Z")
    assert result["state"] == "uncertain"
    replay = adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                                  now="2026-08-01T00:00:02Z")
    assert replay["state"] == "uncertain"
    assert client.create_calls == 1


def test_remote_reconciliation_requires_exact_unique_candidate(tmp_path):
    intent = fixture_intent(tmp_path)
    exact = {"id": "post-123", "content": intent["caption"],
             "publishDate": intent["scheduled_at"],
             "integration": {"id": intent["integration_id"]}, "state": "QUEUE"}
    assert unique_remote_match(intent, [exact])["id"] == "post-123"
    assert unique_remote_match(intent, []) is None
    with pytest.raises(ValueError, match="multiple remote candidates"):
        unique_remote_match(intent, [exact, exact | {"id": "post-456"}])
    wrong = exact | {"integration": {"id": "wrong"}}
    assert unique_remote_match(intent, [wrong]) is None


def test_shadow_path_has_zero_provider_calls(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz()
    result = PostizAdapter(store, client).shadow(intent["publish_key"], "worker", lease["fence"],
                                                  now="2026-08-01T00:00:01Z")
    assert result["status"] == "shadow_valid"
    assert result["external_effects"] == []
    assert client.upload_calls == client.create_calls == client.promote_calls == 0


def test_create_response_for_wrong_integration_is_rejected(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz(create_result=[{"postId": "post-123", "integration": "wrong"}])
    adapter = PostizAdapter(store, client)
    adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                         now="2026-08-01T00:00:01Z")
    with pytest.raises(ValueError, match="Postiz create integration mismatch"):
        adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                             now="2026-08-01T00:00:02Z")
    attempt = store.attempt(stable_id("dispatch", [intent["publish_key"], "create_draft"]))
    assert attempt["state"] == "rejected"
    assert store.get(intent["publish_key"])["state"] == "provider_rejected"


def test_malformed_upload_response_is_rejected_and_not_left_dispatching(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz(upload_result={"id": "media-123", "path": "not-https"})
    adapter = PostizAdapter(store, client)
    with pytest.raises(ValueError, match="https path"):
        adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                             now="2026-08-01T00:00:01Z")
    current = store.get(intent["publish_key"])
    assert current["state"] == "provider_rejected"
    assert "https path" in current["last_error"]


def test_malformed_promote_response_is_rejected_and_never_retried(tmp_path):
    store, intent, lease = setup(tmp_path)
    client = FakePostiz(promote_result={"id": "wrong", "state": "DRAFT"})
    adapter = PostizAdapter(store, client)
    adapter.upload_media(intent["publish_key"], "worker", lease["fence"],
                         now="2026-08-01T00:00:01Z")
    adapter.create_draft(intent["publish_key"], "worker", lease["fence"],
                         now="2026-08-01T00:00:02Z")
    with pytest.raises(ValueError, match="Postiz promote response mismatch"):
        adapter.promote(intent["publish_key"], "worker", lease["fence"],
                        now="2026-08-01T00:00:03Z")
    assert store.get(intent["publish_key"])["state"] == "provider_rejected"
    replay = adapter.promote(intent["publish_key"], "worker", lease["fence"],
                             now="2026-08-01T00:00:04Z")
    assert replay["state"] == "rejected"
    assert client.promote_calls == 1
