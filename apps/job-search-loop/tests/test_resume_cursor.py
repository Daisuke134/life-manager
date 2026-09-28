import unittest
from unittest.mock import AsyncMock, Mock

from job_search_loop.browser_agent.contracts import (
    RowCheckpointV1,
    SessionHandleV1,
)
from job_search_loop.browser_agent.resume_cursor import RowResumer
from job_search_loop.state import provider_recovery_url


class ResumeCursorTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovered_handle_on_another_provider_requires_navigation(self):
        session = Mock()
        handle = SessionHandleV1(1, "http://localhost:9222", "workday-row", "marker", 2)
        session.resume = AsyncMock(return_value=(handle, True))
        session.page.return_value.url = "https://jobs.ashbyhq.com/sierra/role/application"
        checkpoint = RowCheckpointV1(
            1,
            "workday-row",
            "acting",
            "marker",
            1,
            "a" * 64,
            (),
            20,
            "https://jobs.ashbyhq.com/sierra/role/application",
        )
        checkpoints = Mock()
        checkpoints.load.return_value = checkpoint
        evidence = Mock()
        evidence.read_chain.return_value = []
        canonical = "https://example.wd5.myworkdayjobs.com/job/Workday-Role_JR123"

        cursor = await RowResumer(session, checkpoints, evidence).restore(
            "http://localhost:9222",
            "workday-row",
            canonical,
        )

        self.assertTrue(cursor.needs_navigation)
        self.assertEqual(cursor.recovery_url, provider_recovery_url(canonical))


if __name__ == "__main__":
    unittest.main()
