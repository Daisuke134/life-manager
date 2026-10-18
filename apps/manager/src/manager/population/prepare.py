"""Aggregate only leaf estimates and isolate fixed geographic partitions."""
import math
from .acs import FIPS
from .contracts import JointTable, Marginals, PopulationDataError

DEVELOPMENT = ('06','12','17','36','48','53')
VALIDATION = ('04','13','25','37')
CELL_ORDER = ('below_child','below_adult','below_senior','above_child','above_adult','above_senior')
LEAVES = (tuple(range(4,10))+tuple(range(18,24)),tuple(range(10,15))+tuple(range(24,29)),
          (15,16,29,30),tuple(range(33,39))+tuple(range(47,53)),
          tuple(range(39,44))+tuple(range(53,58)),(44,45,58,59))


def aggregate_b17001(row, source):
    try:
        def estimate(i):
            value=row[f'B17001_E{i:03}']
            if not isinstance(value,str) or not value.isascii() or not value.isdecimal():
                raise PopulationDataError(f'invalid estimate E{i:03}')
            return int(value)
        counts=tuple(sum(estimate(i) for i in group) for group in LEAVES)
        if sum(counts[:3]) != estimate(2) or sum(counts[3:]) != estimate(31):
            raise PopulationDataError('leaf sums disagree with poverty totals')
        return JointTable(row['GEO_ID'],source,counts,estimate(1))
    except KeyError as exc: raise PopulationDataError(f'missing ACS item: {exc}') from exc


def marginalize(table):
    x=table.counts
    return Marginals(table.geo_id,table.source,(sum(x[:3]),sum(x[3:])),tuple(x[i]+x[i+3] for i in range(3)),table.total)


def partition_tables(tables):
    ids=[t.geo_id for t in tables]
    expected={'0400000US'+f for f in FIPS}
    if len(ids)!=len(set(ids)) or set(ids)!=expected:
        raise PopulationDataError('expected exactly the 50 states and DC')
    if len({t.source for t in tables})!=1: raise PopulationDataError('mixed source snapshots')
    result={k:[] for k in ('development','validation','test')}
    for table in sorted(tables,key=lambda t:t.geo_id):
        fips=table.geo_id[-2:]
        split='development' if fips in DEVELOPMENT else 'validation' if fips in VALIDATION else 'test'
        result[split].append(table)
    return {key:tuple(value) for key,value in result.items()}


def build_seed(development):
    if len(development)!=6 or {t.geo_id[-2:] for t in development}!=set(DEVELOPMENT):
        raise PopulationDataError('seed must use exactly the six development states')
    if len({t.source for t in development})!=1: raise PopulationDataError('mixed seed sources')
    return tuple(math.fsum(t.counts[i] for t in development) for i in range(6))
