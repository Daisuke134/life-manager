#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lm-distribution" / "postiz_video.py"
SPEC = importlib.util.spec_from_file_location("postiz_video", MODULE_PATH)
postiz_video = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(postiz_video)


class PostizVideoTests(unittest.TestCase):
    def test_resolve_ip_accepts_only_public_ipv4_and_rejects_non_public_values(self):
        self.assertIsNone(postiz_video.validate_resolve_ip(None))
        self.assertEqual(postiz_video.validate_resolve_ip("93.184.216.34"), "93.184.216.34")
        for value in (
            "",
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "192.0.2.1",
            "255.255.255.255",
            "::1",
            "93.184.216.34,1.1.1.1",
            "not-an-ip",
        ):
            with self.subTest(value=value):
                with self.assertRaises(postiz_video.PostizError):
                    postiz_video.validate_resolve_ip(value)

    def test_resolve_override_is_exact_host_only_and_restores_global_resolver(self):
        original = socket.getaddrinfo
        calls = []

        def delegated(host, port, family=0, type=0, proto=0, flags=0):
            calls.append((host, port, family, type, proto, flags))
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(host), port))]

        with patch.object(postiz_video.socket, "getaddrinfo", side_effect=delegated) as delegated_mock:
            with postiz_video.postiz_resolve_override("93.184.216.34"):
                resolved = postiz_video.socket.getaddrinfo("api.postiz.com", 443, 0, socket.SOCK_STREAM)
                self.assertEqual(resolved[0][4][0], "93.184.216.34")
                postiz_video.socket.getaddrinfo("other.example", 443, 0, socket.SOCK_STREAM)
            self.assertIs(postiz_video.socket.getaddrinfo, delegated_mock)
        self.assertIs(postiz_video.socket.getaddrinfo, original)
        self.assertEqual(calls[0][0], "93.184.216.34")
        self.assertEqual(calls[1][0], "other.example")

    def test_main_installs_override_before_first_network_call_and_restores_it(self):
        original = socket.getaddrinfo
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"video")
            caption = Path(directory) / "caption.txt"
            caption.write_text("caption", encoding="utf-8")

            def observe_first_network_call(_api_key):
                self.assertIsNot(postiz_video.socket.getaddrinfo, original)
                raise RuntimeError("stop after resolver install")

            with patch.dict(os.environ, {"POSTIZ_API_KEY": "fixture", "LM_POSTIZ_RESOLVE_IP": "93.184.216.34"}, clear=False):
                with patch.object(sys, "argv", ["postiz_video.py", "--video", str(video), "--caption-file", str(caption), "--integration", "integration-1"]):
                    with patch.object(postiz_video, "read_recent_posts", side_effect=observe_first_network_call):
                        with self.assertRaisesRegex(RuntimeError, "stop after resolver install"):
                            postiz_video.main()
            self.assertIs(postiz_video.socket.getaddrinfo, original)

    def test_payload_is_direct_public_video_with_exact_caption_and_media(self):
        payload = postiz_video.build_payload(
            integration="cmp9txjdp01c8oh0yb6dhlarr",
            caption="Exact caption\n#line",
            title="Life Manager",
            upload_id="upload-1",
            upload_path="https://uploads.example/video.mp4",
            now_iso="2026-07-24T00:00:00.000Z",
        )
        post = payload["posts"][0]
        self.assertEqual(post["integration"]["id"], "cmp9txjdp01c8oh0yb6dhlarr")
        self.assertEqual(post["value"][0]["content"], "Exact caption\n#line")
        self.assertEqual(post["value"][0]["image"], [{"id": "upload-1", "path": "https://uploads.example/video.mp4"}])
        self.assertEqual(post["settings"]["content_posting_method"], "DIRECT_POST")
        self.assertEqual(post["settings"]["privacy_level"], "PUBLIC_TO_EVERYONE")
        self.assertTrue(post["settings"]["video_made_with_ai"])

    def test_instagram_carousel_payload_preserves_order_and_native_post_settings(self):
        payload = postiz_video.build_payload(
            integration="cmq3sq7mc000eqp0y7azfm8yk",
            caption="メンタルが勝手に安定する\n口癖５選",
            title="Life Manager",
            upload_ids=["upload-1", "upload-2", "upload-3"],
            upload_paths=["https://uploads.example/1.jpg", "https://uploads.example/2.jpg", "https://uploads.example/3.jpg"],
            now_iso="2026-08-26T07:30:00.000Z",
            platform="instagram",
        )
        post = payload["posts"][0]
        self.assertEqual(post["integration"]["id"], "cmq3sq7mc000eqp0y7azfm8yk")
        self.assertEqual(post["settings"], {
            "__type": "instagram-standalone",
            "post_type": "post",
            "is_trial_reel": False,
            "collaborators": [],
        })
        self.assertEqual([item["id"] for item in post["value"][0]["image"]], ["upload-1", "upload-2", "upload-3"])
        self.assertEqual([item["path"] for item in post["value"][0]["image"]], [
            "https://uploads.example/1.jpg", "https://uploads.example/2.jpg", "https://uploads.example/3.jpg",
        ])

    def test_tiktok_photo_carousel_payload_preserves_order_and_direct_post_settings(self):
        payload = postiz_video.build_payload(
            integration="cmnenjkff01j1pa0ysufmzhfr",
            caption="Exact EN caption",
            title="Procrastination isn't laziness",
            upload_ids=[f"upload-{index}" for index in range(1, 7)],
            upload_paths=[f"https://uploads.example/{index}.jpg" for index in range(1, 7)],
            now_iso="2026-08-26T06:00:00.000Z",
            platform="tiktok",
        )
        post = payload["posts"][0]
        self.assertEqual(post["integration"]["id"], "cmnenjkff01j1pa0ysufmzhfr")
        self.assertEqual([item["path"] for item in post["value"][0]["image"]], [f"https://uploads.example/{index}.jpg" for index in range(1, 7)])
        self.assertEqual(post["settings"]["__type"], "tiktok")
        self.assertEqual(post["settings"]["content_posting_method"], "DIRECT_POST")
        self.assertEqual(post["settings"]["autoAddMusic"], "yes")

    def test_tiktok_photo_carousel_rejects_direct_video_url_without_photo_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            images = []
            for index in range(1, 7):
                image = Path(directory) / f"{index}.jpg"
                image.write_bytes(b"\xff\xd8\xff" + bytes([index]))
                images.append(image)
            args = SimpleNamespace(image=images, platform="tiktok", integration="cmnenjkff01j1pa0ysufmzhfr", title="Exact hook", video=None)
            payloads = []
            with patch.object(postiz_video, "upload_image", side_effect=lambda image, _key: (image.stem, f"https://uploads.example/{image.name}")):
                with patch.object(postiz_video, "create_post", side_effect=lambda payload, _key: payloads.append(payload) or "postiz-1"):
                    with patch.object(postiz_video, "read_publish_state", return_value={"state": "PUBLISHED", "post_url": "https://www.tiktok.com/@anicca_slideshow/video/7777777777777777777"}):
                        with patch.object(postiz_video.time, "sleep"):
                            with patch.object(postiz_video, "resolve_profile_release_url") as resolver:
                                with patch("builtins.print") as output:
                                    with self.assertRaisesRegex(postiz_video.PostizError, "terminal state"):
                                        postiz_video._publish(args, "token", "Exact caption")
            resolver.assert_not_called()
            result = json.loads(output.call_args.args[0])
            self.assertFalse(result["reconciled"])
            self.assertEqual(result["post_url"], "https://www.tiktok.com/@anicca_slideshow/video/7777777777777777777")
            self.assertEqual(payloads[0]["posts"][0]["settings"]["title"], "Exact hook")
            self.assertEqual(len(payloads[0]["posts"][0]["value"][0]["image"]), 6)

    def test_carousel_payload_rejects_short_or_video_image_mix(self):
        with self.assertRaises(postiz_video.PostizError):
            postiz_video.build_payload(
                integration="i", caption="caption", title="title",
                upload_ids=["upload-1"], upload_paths=["https://uploads.example/1.jpg"],
                now_iso="2026-08-26T07:30:00.000Z", platform="instagram",
            )
        with self.assertRaises(postiz_video.PostizError):
            postiz_video.build_payload(
                integration="i", caption="caption", title="title",
                upload_ids=["upload-1", "upload-2"], upload_paths=["1.jpg", "2.mp4"],
                now_iso="2026-08-26T07:30:00.000Z", platform="tiktok",
            )

    def test_image_upload_rejects_empty_and_non_jpeg_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.jpg"
            empty.write_bytes(b"")
            with self.assertRaises(postiz_video.PostizError):
                postiz_video.upload_image(empty, "token")
            png = Path(directory) / "image.png"
            png.write_bytes(b"\x89PNG\r\n")
            with self.assertRaises(postiz_video.PostizError):
                postiz_video.upload_image(png, "token")

    def test_carousel_caption_reader_preserves_raw_utf8_while_video_reader_trims(self):
        with tempfile.TemporaryDirectory() as directory:
            caption_file = Path(directory) / "caption.txt"
            raw_caption = " \nExact caption\n  \n"
            caption_file.write_text(raw_caption, encoding="utf-8")
            self.assertEqual(postiz_video.read_caption(caption_file, carousel=True), raw_caption)
            self.assertEqual(postiz_video.read_caption(caption_file, carousel=False), raw_caption.strip())

    def test_direct_carousel_url_only_accepts_instagram_post(self):
        self.assertTrue(postiz_video._valid_instagram_carousel_url("https://www.instagram.com/p/ABC_123/"))
        self.assertFalse(postiz_video._valid_instagram_carousel_url("https://www.instagram.com/reel/ABC_123/"))
        self.assertFalse(postiz_video._valid_instagram_carousel_url("https://www.instagram.com/@ani.cca1234"))
        self.assertFalse(postiz_video._valid_instagram_carousel_url("https://www.instagram.com/p/12345678901234567890/"))
        self.assertTrue(postiz_video._valid_public_url("instagram", "https://www.instagram.com/reel/ABC_123/"))

    def test_extract_post_id_accepts_the_real_postiz_array_shape_only(self):
        self.assertEqual(postiz_video.extract_post_id([{"postId": "post-1"}]), "post-1")
        with self.assertRaises(postiz_video.PostizError):
            postiz_video.extract_post_id({"id": "upload-id-is-not-post-id"})

    def test_find_published_requires_state_and_public_release_url(self):
        rows = {
            "posts": [
                {"id": "p1", "state": "QUEUE", "releaseURL": None},
                {"id": "p2", "state": "PUBLISHED", "releaseURL": "https://www.tiktok.com/@life/video/123"},
            ]
        }
        self.assertEqual(
            postiz_video.find_post(rows, "p2"),
            {"state": "PUBLISHED", "post_url": "https://www.tiktok.com/@life/video/123"},
        )
        self.assertEqual(postiz_video.find_post(rows, "p1"), {"state": "QUEUE", "post_url": None})

    def test_find_post_reconciles_exact_tiktok_photo_proof_without_inventing_video_url(self):
        caption = "Exact caption\n#line"
        row = {
            "id": "photo-1",
            "state": "PUBLISHED",
            "releaseURL": "https://www.tiktok.com/@anicca_slideshow",
            "releaseId": "p_pub_url~v2.7679813128503363591",
            "integration": {"id": "cmnenjkff01j1pa0ysufmzhfr"},
            "content": caption,
            "settings": json.dumps({
                "__type": "tiktok",
                "title": "Exact hook",
                "content_posting_method": "DIRECT_POST",
            }),
        }
        self.assertEqual(
            postiz_video.find_post([row], "photo-1", "tiktok"),
            {
                "state": "PUBLISHED",
                "post_url": None,
                "integration_id": "cmnenjkff01j1pa0ysufmzhfr",
                "content_sha256": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
                "title": "Exact hook",
                "posting_method": "DIRECT_POST",
                "release_id": "p_pub_url~v2.7679813128503363591",
            },
        )

    def test_find_post_rejects_incomplete_tiktok_photo_proof(self):
        base = {
            "id": "photo-invalid",
            "state": "PUBLISHED",
            "releaseURL": "https://www.tiktok.com/@anicca_slideshow",
            "releaseId": "p_pub_url~v2.7679813128503363591",
            "integration": {"id": "cmnenjkff01j1pa0ysufmzhfr"},
            "content": "Exact caption",
            "settings": {
                "__type": "tiktok",
                "title": "Exact hook",
                "content_posting_method": "DIRECT_POST",
            },
        }
        invalid_rows = (
            {**base, "releaseURL": ""},
            {**base, "releaseId": "p_pub_url~v2.7679813128503363591-extra"},
            {**base, "settings": {**base["settings"], "__type": "instagram"}},
            {**base, "settings": {**base["settings"], "title": "  "}},
            {**base, "settings": {**base["settings"], "content_posting_method": "UPLOAD"}},
            {**base, "integration": {"id": ""}},
            {**base, "content": None},
        )
        for row in invalid_rows:
            with self.subTest(row=row):
                with self.assertRaises(postiz_video.PostizError):
                    postiz_video.find_post([row], row["id"], "tiktok")

    def test_tiktok_photo_carousel_publish_accepts_exact_postiz_api_proof_without_url(self):
        with tempfile.TemporaryDirectory() as directory:
            images = []
            for index in range(1, 7):
                image = Path(directory) / f"{index}.jpg"
                image.write_bytes(b"\xff\xd8\xff" + bytes([index]))
                images.append(image)
            args = SimpleNamespace(
                image=images,
                platform="tiktok",
                integration="cmnenjkff01j1pa0ysufmzhfr",
                title="Exact hook",
                video=None,
            )
            caption = "Exact caption"
            row = {
                "id": "photo-1",
                "state": "PUBLISHED",
                "releaseURL": "https://www.tiktok.com/@anicca_slideshow",
                "releaseId": "p_pub_url~v2.7679813128503363591",
                "integration": {"id": args.integration},
                "content": caption,
                "settings": json.dumps({
                    "__type": "tiktok",
                    "title": args.title,
                    "content_posting_method": "DIRECT_POST",
                }),
            }
            with patch.object(
                postiz_video,
                "upload_image",
                side_effect=lambda image, _key: (image.stem, f"https://uploads.example/{image.name}"),
            ):
                with patch.object(postiz_video, "create_post", return_value="postiz-photo-1"):
                    with patch.object(
                        postiz_video,
                        "read_publish_state",
                        side_effect=lambda post_id, _key, platform: postiz_video.find_post(
                            {"posts": [{**row, "id": post_id}]}, post_id, platform,
                        ),
                    ):
                        with patch.object(postiz_video.time, "sleep"):
                            with patch.object(postiz_video, "resolve_profile_release_url") as resolver:
                                with patch("builtins.print") as output:
                                    self.assertEqual(postiz_video._publish(args, "token", caption), 0)
            resolver.assert_not_called()
            result = json.loads(output.call_args.args[0])
            self.assertEqual(result["state"], "PUBLISHED")
            self.assertIsNone(result["post_url"])
            self.assertTrue(result["reconciled"])
            self.assertEqual(result["integration_id"], args.integration)
            self.assertEqual(result["content_sha256"], hashlib.sha256(caption.encode("utf-8")).hexdigest())
            self.assertEqual(result["title"], args.title)
            self.assertEqual(result["posting_method"], "DIRECT_POST")
            self.assertEqual(result["release_id"], row["releaseId"])

    def test_published_exact_video_state_is_provider_reconciled(self):
        self.assertTrue(postiz_video.is_reconciled_state({
            "state": "PUBLISHED",
            "post_url": "https://www.tiktok.com/@life/video/123",
        }))
        self.assertFalse(postiz_video.is_reconciled_state({
            "state": "PUBLISHED",
            "post_url": "https://www.tiktok.com/@life",
        }))
        self.assertTrue(postiz_video.is_reconciled_state({
            "state": "PUBLISHED",
            "post_url": None,
            "integration_id": "integration-1",
            "content_sha256": "a" * 64,
            "title": "Exact hook",
            "posting_method": "DIRECT_POST",
            "release_id": "p_pub_url~v2.7679813128503363591",
        }))
        self.assertFalse(postiz_video.is_reconciled_state({
            "state": "PUBLISHED",
            "post_url": None,
            "integration_id": "integration-1",
            "content_sha256": "a" * 64,
            "title": "Exact hook",
            "posting_method": "DIRECT_POST",
            "release_id": "p_pub_url~v2.7679813128503363591-extra",
        }))

    def test_find_post_rejects_published_without_public_url(self):
        with self.assertRaises(postiz_video.PostizError):
            postiz_video.find_post([{"id": "p", "state": "PUBLISHED"}], "p")

    def test_find_post_derives_tiktok_candidate_only_from_exact_published_row(self):
        row = {
            "id": "post-1",
            "state": "PUBLISHED",
            "releaseURL": "https://www.tiktok.com/@life.manager",
            "releaseId": "v_pub_file~v2-1.7999999999999999999",
        }
        self.assertEqual(
            postiz_video.find_post([row], "post-1"),
            {"state": "PUBLISHED", "post_url": "https://www.tiktok.com/@life.manager/video/7999999999999999999"},
        )

    def test_caption_only_provider_effect_never_reconciles_a_different_video(self):
        rows = {
            "posts": [{
                "id": "post-1",
                "state": "PUBLISHED",
                "content": "Exact caption\n#line",
                "integration": {"id": "integration-1"},
                "releaseURL": "https://www.tiktok.com/@life/video/222",
                "releaseId": "internal-provider-id",
            }],
        }
        self.assertIsNone(
            postiz_video.find_existing_post(
                rows,
                integration="integration-1",
                caption="Exact caption\n#line",
                video_sha256="b" * 64,
            ),
        )

    def test_existing_published_row_is_not_reused_without_public_readback(self):
        rows = {
            "posts": [{
                "id": "post-1",
                "state": "PUBLISHED",
                "content": "Exact caption\n#line",
                "integration": {"id": "integration-1"},
                "releaseURL": "https://www.tiktok.com/@life/video/222",
                "releaseId": "v_pub_file~v2-1.222",
                "publishDate": "2026-09-18T00:00:00Z",
                "lifeManagerVideoSha256": "b" * 64,
            }],
        }
        with patch.object(postiz_video, "verify_tiktok_public_url", return_value=False):
            with self.assertRaisesRegex(postiz_video.PostizError, "public readback"):
                postiz_video.find_existing_post(
                    rows,
                    integration="integration-1",
                    caption="Exact caption\n#line",
                    video_sha256="b" * 64,
                )

    def test_profile_release_url_resolves_to_matching_recent_video(self):
        payload = {
            "entries": [
                {
                    "id": "111",
                    "url": "https://www.tiktok.com/@life/video/111",
                    "title": "unrelated old post",
                    "timestamp": 100,
                },
                {
                    "id": "222",
                    "url": "https://www.tiktok.com/@life/video/222",
                    "title": "Exact caption first line and more",
                    "timestamp": 205,
                },
            ]
        }

        def runner(*_args, **_kwargs):
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

        url = postiz_video.resolve_profile_release_url(
            "https://www.tiktok.com/@life",
            "Exact caption first line\nand more",
            posted_after=200,
            runner=runner,
        )
        self.assertEqual(url, "https://www.tiktok.com/@life/video/222")

    def test_profile_resolution_rejects_old_or_caption_mismatched_entries(self):
        payload = {
            "entries": [
                {
                    "id": "111",
                    "url": "https://www.tiktok.com/@life/video/111",
                    "title": "Exact caption first line",
                    "timestamp": 100,
                },
                {
                    "id": "222",
                    "url": "https://www.tiktok.com/@life/video/222",
                    "title": "wrong current post",
                    "timestamp": 205,
                },
            ]
        }

        def runner(*_args, **_kwargs):
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

        self.assertIsNone(
            postiz_video.resolve_profile_release_url(
                "https://www.tiktok.com/@life",
                "Exact caption first line",
                posted_after=200,
                runner=runner,
                browser_resolver=lambda *_args, **_kwargs: None,
            )
        )

    def test_profile_only_post_never_falls_back_to_browser(self):
        calls = []

        def browser(profile_url, caption, *, posted_after, caption_prefix):
            calls.append((profile_url, caption, posted_after, caption_prefix))
            return "https://www.tiktok.com/@honne_reveal/video/7676388327427149077"

        result = postiz_video.resolve_profile_release_url(
            "https://www.tiktok.com/@honne_reveal",
            "someone tell me\nthis is illegal",
            posted_after=1_777_000_000,
            runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", ""),
            browser_resolver=browser,
        )
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_profile_caption_join_rejects_an_old_duplicate(self):
        rows = [
            {"href": "https://www.tiktok.com/@life/video/7676852644698262791", "alt": "Exact caption #tag"},
            {"href": "https://www.tiktok.com/@life/video/7676422253638176020", "alt": "Exact caption #tag"},
        ]
        self.assertEqual(
            postiz_video._matching_profile_url(rows, "exact caption", 1_787_406_536),
            "https://www.tiktok.com/@life/video/7676852644698262791",
        )
        self.assertIsNone(postiz_video._matching_profile_url(rows[1:], "exact caption", 1_787_406_536))

    def test_tiktok_public_readback_accepts_only_the_exact_captioned_video_url(self):
        observed = []

        def browser(profile_url, caption, *, posted_after, caption_prefix):
            observed.append((profile_url, caption, posted_after, caption_prefix))
            return "https://www.tiktok.com/@life/video/222"

        self.assertTrue(
            postiz_video.verify_tiktok_public_url(
                "https://www.tiktok.com/@life/video/222",
                "Exact caption\n#line",
                posted_after=200,
                browser_resolver=browser,
            )
        )
        self.assertEqual(observed[0][0], "https://www.tiktok.com/@life")

    def test_tiktok_public_readback_rejects_provider_url_when_profile_shows_another_video(self):
        def browser(*_args, **_kwargs):
            return "https://www.tiktok.com/@life/video/333"

        self.assertFalse(
            postiz_video.verify_tiktok_public_url(
                "https://www.tiktok.com/@life/video/222",
                "Exact caption\n#line",
                posted_after=200,
                browser_resolver=browser,
            )
        )


if __name__ == "__main__":
    unittest.main()
