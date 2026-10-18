import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from manager.population.acs import read_acs_extract, fetch_acs_extract
from manager.population.contracts import PopulationDataError
from helpers import fixture_bytes, write_fixture

class AcsTests(unittest.TestCase):
    def test_extract_manifest_hash_matches_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=write_fixture(d)
            src,rows=read_acs_extract(p)
            self.assertEqual(len(rows),52)
            p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaises(PopulationDataError): read_acs_extract(p)

    def test_rejects_html_wrong_table_and_missing_header(self):
        raw=fixture_bytes()
        for data in [b'<html>missing key</html>',raw.replace(b'B17001_',b'B17001E_'),raw.split(b'\n',1)[1]]:
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(PopulationDataError): read_acs_extract(write_fixture(d,data))

    def test_rejects_duplicate_missing_and_negative_estimates(self):
        lines=fixture_bytes().splitlines(keepends=True)
        bad=lines[1].decode().split('|'); bad[1]='-666666666'
        variants=[b''.join(lines[:-1]),b''.join(lines+[lines[1]]),
                  lines[0]+'|'.join(bad).encode()+b''.join(lines[2:])]
        for data in variants:
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(PopulationDataError): read_acs_extract(write_fixture(d,data))

    def test_fetch_is_bounded_and_does_not_publish_incomplete_snapshot(self):
        for data,limit in [(fixture_bytes(),100),(fixture_bytes().split(b'\n',2)[0]+b'\n',8388608)]:
            with tempfile.TemporaryDirectory() as d, patch('manager.population.acs.urlopen',return_value=io.BytesIO(data)):
                with self.assertRaises(PopulationDataError):fetch_acs_extract(Path(d)/'input',max_bytes=limit)
                self.assertFalse((Path(d)/'input/source.json').exists())

    def test_fetch_validates_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as d, patch('manager.population.acs.urlopen',return_value=io.BytesIO(fixture_bytes())):
            src=fetch_acs_extract(Path(d)/'input')
            src2,rows=read_acs_extract(Path(d)/'input/source.dat')
            self.assertEqual(src,src2);self.assertEqual(len(rows),52)
