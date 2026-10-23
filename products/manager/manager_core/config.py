"""MGR-001: fail-closed scaffolding; no live effects or private data."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeDefaults:
    # Deliberately NOT environment-variable toggles.
    # Future effectful actions must use an independent, audited authority service.
    live_external_writes: bool = False
    public_posting: bool = False
    money_transfer: bool = False
    physical_actuation: bool = False
    private_person_data: bool = False

    def __post_init__(self):
        if any((self.live_external_writes, self.public_posting,
                self.money_transfer, self.physical_actuation,
                self.private_person_data)):
            raise ValueError("Scaffold denies all live effects and private data")


DEFAULTS = RuntimeDefaults()
