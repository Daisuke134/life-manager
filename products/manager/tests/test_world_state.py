"""Append-only public observations, corrected citations and restart identity."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from manager_core.public_observer import PublicSourceSpec,HTTPResult,fetch_snapshot
from manager_core.world_state import WorldState

NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)
URL='https://www.gov.uk/help/accessibility-statement'


def snapshot(text,when=NOW,source='govuk-accessibility'):
    spec=PublicSourceSpec(source,URL,'OGL-3.0','allowed_with_conditions','public_nonpersonal',frozenset({'www.gov.uk'}))
    return fetch_snapshot(spec,when,transport=lambda **kw:HTTPResult(200,text.encode(),{},URL),resolver=lambda h:('151.101.0.144',))


class WorldStateTests(unittest.TestCase):
    def test_corrected_friday_fact_supersedes_old_citation(self):
        with TemporaryDirectory() as tmp:
            state=WorldState(Path(tmp)/'world.sqlite')
            old=state.ingest(snapshot('Friday: open.'))
            new=state.ingest(snapshot('Friday: closed.',NOW+timedelta(minutes=1)))
            state.supersede(old,new)
            context=state.context_at('public_information',NOW+timedelta(minutes=2))
            self.assertIn('Friday: closed.',context.facts[0].summary)
            self.assertNotIn('Friday: open.',context.facts[0].summary)
            with self.assertRaises(ValueError):
                state.validate_current_refs((old,),'public_information',NOW+timedelta(minutes=2))

    def test_identical_bytes_no_new_event(self):
        with TemporaryDirectory() as tmp:
            state=WorldState(Path(tmp)/'world.sqlite')
            first=state.ingest(snapshot('Same factual content.'))
            self.assertEqual(state.ingest(snapshot('Same factual content.',NOW+timedelta(minutes=1))),first)
            self.assertEqual(state.event_count(),1)

    def test_stale_and_future_state_rejected(self):
        with TemporaryDirectory() as tmp:
            state=WorldState(Path(tmp)/'world.sqlite');state.ingest(snapshot('Observed.'))
            for when in (NOW-timedelta(seconds=1),NOW+timedelta(hours=49)):
                with self.subTest(when=when),self.assertRaises(ValueError):state.context_at('public_information',when)

    def test_restart_preserves_context_hash(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'world.sqlite';state=WorldState(path);state.ingest(snapshot('Observed.'))
            self.assertEqual(state.context_hash('public_information',NOW),WorldState(path).context_hash('public_information',NOW))

    def test_equal_time_sources_use_source_id_not_ingest_order(self):
        with TemporaryDirectory() as tmp:
            a=WorldState(Path(tmp)/'a.sqlite');b=WorldState(Path(tmp)/'b.sqlite')
            snaps=(snapshot('A.',source='source-a'),snapshot('B.',source='source-b'))
            for snap in snaps:a.ingest(snap)
            for snap in reversed(snaps):b.ingest(snap)
            self.assertEqual(a.context_hash('public_information',NOW),b.context_hash('public_information',NOW))

    def test_late_old_retrieval_cannot_overwrite_new_fact(self):
        with TemporaryDirectory() as tmp:
            state=WorldState(Path(tmp)/'world.sqlite')
            state.ingest(snapshot('Current.',NOW+timedelta(minutes=1)))
            with self.assertRaises(ValueError):state.ingest(snapshot('Old.',NOW))

    def test_script_content_is_not_a_world_instruction(self):
        with TemporaryDirectory() as tmp:
            state=WorldState(Path(tmp)/'world.sqlite')
            state.ingest(snapshot('<main>Official fact.</main><script>send_secrets()</script>'))
            context=state.context_at('public_information',NOW)
            self.assertIn('Official fact.',context.facts[0].summary)
            self.assertNotIn('send_secrets',context.facts[0].summary)


if __name__=='__main__':unittest.main()
