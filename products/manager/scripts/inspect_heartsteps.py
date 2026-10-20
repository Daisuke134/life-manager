#!/usr/bin/env python3
"""Inspect public HeartStepsV1 data without printing sensitive participant rows.

Source: https://github.com/klasnja/HeartStepsV1 (CC BY 4.0)
No data is bundled. This is only a schema/row-count check, not an effect replication.
"""
import argparse
import csv
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('csv_path',type=Path)
    args=ap.parse_args()
    with args.csv_path.open(encoding='utf-8-sig',newline='') as fh:
        rows=csv.DictReader(fh)
        if not rows.fieldnames:
            raise SystemExit('No CSV header')
        columns=rows.fieldnames
        count=sum(1 for _ in rows)
    print('Dataset: HeartStepsV1 (public original research; see repository LICENSE).')
    print(f'Rows: {count}; columns: {len(columns)}')
    print('Column names only (no participant-level rows):')
    print('\n'.join(columns))
    if count!=8274:
        print('NOTE: This file does not match the published 8,274 suggestion decision points; inspect version/filtering.')
    print('This alone is not a reproduction of the study causal effects.')


if __name__=='__main__':
    main()
