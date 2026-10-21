"""K014: adversarial, deterministic offline provider/sensor pair for two domains."""
from datetime import datetime, timezone
from manager_core.verifier import ExternalReadback


class OfflineFixtureAdapter:
    offline_fixture=True
    executor_source="fixture-executor"

    def __init__(self,domain,action,target,*,timeout_after_effect=False,timeout_before_effect=False):
        if domain not in {"finance","environment"}:
            raise ValueError("only fixture domains are supported")
        self.domain,self.action,self.target=domain,action,target
        self.timeout_after_effect=timeout_after_effect
        self.timeout_before_effect=timeout_before_effect
        self.lookup_fails=False
        self.effects={}
        self.send_calls=0

    def send(self,key):
        self.send_calls+=1
        if self.timeout_before_effect:
            raise TimeoutError("simulated timeout BEFORE provider effect")
        ref="receipt-"+key
        self.effects[key]=ref
        if self.timeout_after_effect:
            raise TimeoutError("simulated timeout AFTER the provider effect")
        return ref

    def lookup(self,key):
        if self.lookup_fails:
            raise TimeoutError("fixture provider temporarily unreachable")
        return ("PRESENT",self.effects[key]) if key in self.effects else ("ABSENT",None)


class OfflineFixtureSensor:
    source="fixture-sensor"

    def __init__(self,adapter: OfflineFixtureAdapter):
        self.adapter=adapter

    def readback(self,key,at: datetime):
        ref=self.adapter.effects.get(key)
        if ref is None: return None
        return ExternalReadback(key,self.source,self.adapter.executor_source,at,
                                10.0,ref)
