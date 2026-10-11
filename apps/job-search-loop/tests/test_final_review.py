import unittest
from pathlib import Path

from job_search_loop.browser_agent.contracts import (
    ObservationV1,
    ResumeVerificationV1,
)
from job_search_loop.browser_agent.review import verify_final_review


class FinalReviewTests(unittest.TestCase):
    def test_localized_workday_title_binds_role_through_exact_requisition_url(self):
        observation = ObservationV1(
            1,
            url=(
                "https://rakuten.wd1.myworkdayjobs.com/ja-JP/rakuteninc/job/"
                "Tokyo/English-Role_1035746-62/apply/autofillWithResume"
            ),
            title="AI検索マーケティングの未来を創る プロダクト担当",
            visible_text="送信",
            controls=(), validation_text=(), tabs=(),
            screenshot_path=Path("review.png"),
            screenshot_sha256="a" * 64, content_sha256="b" * 64,
        )
        resume = ResumeVerificationV1(
            1, observation_sha256=observation.content_sha256,
            resume_sha256="c" * 64, filename_visible=True,
            checked_labels=("Resume",), mismatched_labels=(),
            receipt_sha256="d" * 64,
        )

        receipt = verify_final_review(
            row_run_id="row-run", application_id="application",
            company="Rakuten", role="Product & Growth Specialist",
            expected_url=(
                "https://rakuten.wd1.myworkdayjobs.com/rakuteninc/job/"
                "Tokyo/English-Role_1035746-62"
            ),
            expected_resume_sha256="c" * 64,
            observation=observation, resume=resume,
        )

        self.assertTrue(receipt.role_visible)

    def test_review_rejects_a_local_pdf_that_is_not_the_visible_attachment(self):
        observation = ObservationV1(1, url="https://jobs.ashbyhq.com/example/role/application", title="Engineer @ Example", visible_text="Review Submit", controls=(), validation_text=(), tabs=(), screenshot_path=Path("review.png"), screenshot_sha256="a"*64, content_sha256="b"*64)
        resume = ResumeVerificationV1(1, observation_sha256=observation.content_sha256, resume_sha256="c"*64, filename_visible=False, checked_labels=(), mismatched_labels=(), receipt_sha256="d"*64)
        with self.assertRaisesRegex(RuntimeError, "routed resume filename"):
            verify_final_review(row_run_id="row", application_id="application", company="Example", role="Engineer", expected_url="https://jobs.ashbyhq.com/example/role", expected_resume_sha256="c"*64, observation=observation, resume=resume)

    def test_single_page_ats_binds_company_and_role_from_document_title(self):
        observation = ObservationV1(
            1,
            url="https://jobs.ashbyhq.com/langchain/role/application",
            title="Solutions Architect (APAC) @ LangChain",
            visible_text="Application Submit Application",
            controls=(),
            validation_text=(),
            tabs=(),
            screenshot_path=Path("review.png"),
            screenshot_sha256="a" * 64,
            content_sha256="b" * 64,
        )
        resume = ResumeVerificationV1(
            1,
            observation_sha256=observation.content_sha256,
            resume_sha256="c" * 64,
            filename_visible=True,
            checked_labels=("Resume",),
            mismatched_labels=(),
            receipt_sha256="d" * 64,
        )

        receipt = verify_final_review(
            row_run_id="row-run",
            application_id="application",
            company="LangChain",
            role="Solutions Architect (APAC)",
            expected_url="https://jobs.ashbyhq.com/langchain/role",
            expected_resume_sha256="c" * 64,
            observation=observation,
            resume=resume,
        )

        self.assertTrue(receipt.company_visible)
        self.assertTrue(receipt.role_visible)


if __name__ == "__main__":
    unittest.main()
