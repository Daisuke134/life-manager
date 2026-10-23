"""K006: explicit intervention protocol, including UNKNOWN and irreversible stop states."""
from enum import Enum


class State(str, Enum):
    OBSERVED = "OBSERVED"
    HYPOTHESIZED = "HYPOTHESIZED"
    PROPOSED = "PROPOSED"
    RISK_CHECKED = "RISK_CHECKED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    EVALUATED = "EVALUATED"
    LEARNED = "LEARNED"
    NO_ACTION = "NO_ACTION"
    REJECTED = "REJECTED"
    UNKNOWN_EFFECT = "UNKNOWN_EFFECT"
    MEASUREMENT_MISSING = "MEASUREMENT_MISSING"
    ROLLBACK_REQUESTED = "ROLLBACK_REQUESTED"
    ROLLED_BACK = "ROLLED_BACK"


LEGAL = {
    State.OBSERVED: {State.HYPOTHESIZED, State.NO_ACTION, State.REJECTED},
    State.HYPOTHESIZED: {State.PROPOSED, State.NO_ACTION, State.REJECTED},
    State.PROPOSED: {State.RISK_CHECKED, State.NO_ACTION, State.REJECTED},
    State.RISK_CHECKED: {State.AUTHORIZED, State.NO_ACTION, State.REJECTED},
    State.AUTHORIZED: {State.EXECUTED, State.UNKNOWN_EFFECT, State.REJECTED},
    State.EXECUTED: {State.VERIFIED, State.MEASUREMENT_MISSING, State.UNKNOWN_EFFECT},
    State.VERIFIED: {State.EVALUATED, State.MEASUREMENT_MISSING},
    State.EVALUATED: {State.LEARNED, State.ROLLBACK_REQUESTED},
    State.LEARNED: {State.ROLLBACK_REQUESTED},
    State.ROLLBACK_REQUESTED: {State.ROLLED_BACK},
    State.UNKNOWN_EFFECT: {State.MEASUREMENT_MISSING},
    State.MEASUREMENT_MISSING: set(),
    State.NO_ACTION: set(),
    State.REJECTED: set(),
    State.ROLLED_BACK: set(),
}


class StateMachine:
    def __init__(self, state=State.OBSERVED):
        if not isinstance(state, State):
            raise ValueError("valid initial state required")
        self.state = state
        self.history = [state]

    def transition(self, next_state: State) -> State:
        if not isinstance(next_state, State) or next_state not in LEGAL[self.state]:
            raise ValueError(f"illegal Manager transition {self.state} -> {next_state}")
        self.state = next_state
        self.history.append(next_state)
        return self.state
