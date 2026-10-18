"""Immutable household/person contracts for occupied Rhode Island housing units."""
from dataclasses import dataclass
import re
from .contracts import PopulationDataError


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise PopulationDataError(f'{name}: expected integer in [{low},{high}]')


def serial(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z0-9]{1,32}',value):
        raise PopulationDataError('invalid PUMS SERIALNO')


@dataclass(frozen=True)
class Person:
    serialno: str
    order: int
    age: int
    sex: int
    relationship: int
    weight: int

    def __post_init__(self):
        serial(self.serialno);integer(self.order,1,20,'SPORDER');integer(self.age,0,99,'AGEP')
        integer(self.sex,1,2,'SEX');integer(self.relationship,20,38,'RELSHIPP');integer(self.weight,1,9999,'PWGTP')


@dataclass(frozen=True)
class Household:
    serialno: str
    size: int
    hht: int
    weight: int
    persons: tuple[Person,...]

    def __post_init__(self):
        serial(self.serialno);integer(self.size,1,20,'NP');integer(self.hht,1,7,'HHT');integer(self.weight,1,9999,'WGTP')
        if not isinstance(self.persons,tuple) or len(self.persons)!=self.size or any(not isinstance(p,Person) for p in self.persons):
            raise PopulationDataError('household must contain its complete immutable member tuple')
        if any(p.serialno!=self.serialno or p.relationship>=37 for p in self.persons):
            raise PopulationDataError('person belongs to another household/universe')
        if tuple(p.order for p in self.persons)!=tuple(range(1,self.size+1)):
            raise PopulationDataError('duplicate, missing or unsorted person order')
        if sum(p.relationship==20 for p in self.persons)!=1:
            raise PopulationDataError('expected exactly one reference person')
        if (self.hht in (1,2,3,5,7) and self.size<2) or (self.hht in (4,6) and self.size!=1):
            raise PopulationDataError('HHT and household size disagree')


@dataclass(frozen=True)
class HouseholdControls:
    total: int
    family: tuple[int,int]
    size: tuple[int,int,int]

    def __post_init__(self):
        integer(self.total,1,1000000,'target households')
        for name,values,length in [('family',self.family,2),('size',self.size,3)]:
            if not isinstance(values,tuple) or len(values)!=length:raise PopulationDataError(f'invalid {name} target')
            for value in values:integer(value,0,self.total,name)
            if sum(values)!=self.total:raise PopulationDataError(f'{name} does not sum to total')
        if self.family[0]>self.total-self.size[0]:raise PopulationDataError('family household cannot be a one-person household')


def cell_index(household):
    return (0 if household.hht<=3 else 3)+min(household.size,3)-1
