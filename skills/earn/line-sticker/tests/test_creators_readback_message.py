import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import creators_readback as MODULE  # noqa: E402

# Body text of message 8567923 (48137583 rejection, 2026-10-08), trimmed.
REPLY_FORM_BODY = ("リジェクト\nメッセージ\nLINE\n2026.10.08 16:09:34\n"
                   "申請されたスタンプは、特集の参加条件を満たしておりませんでした。\n\n"
                   "以下のフォームからメッセージを送信することができます。\n\n送信")


class ExtractMessage(unittest.TestCase):
    def test_reply_form_footer_ends_the_message(self) -> None:
        self.assertEqual(MODULE.extract_message(REPLY_FORM_BODY),
                         "申請されたスタンプは、特集の参加条件を満たしておりませんでした。")

    def test_no_reply_footer_still_ends_the_message(self) -> None:
        body = "2026.10.06 14:21:00\n枚数不足\nこのメッセージに返信することはできません。"
        self.assertEqual(MODULE.extract_message(body), "枚数不足")


if __name__ == "__main__":
    unittest.main()
