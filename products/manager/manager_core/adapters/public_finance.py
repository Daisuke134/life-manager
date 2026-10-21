"""F003 public finance ledger READ ONLY. Historical facts are not Manager effects.

The only outbound destination is Open Collective's public GraphQL v2 API.
A fixed query returns a small ledger sample (no donor names, email or payment
details); unknown responses never mean zero. No private token, mutation,
transfer, account management or donation is supported.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from urllib.request import Request, urlopen

ENDPOINT="https://api.opencollective.com/graphql/v2"
# The static GraphQL query cannot be changed by an account slug.
QUERY="""query ManagerReadOnlyPublicLedger($slug: String!) {
  account(slug: $slug) {
    slug
    transactions(limit: 4) {
      totalCount
      nodes {
        id
        type
        kind
        amount { valueInCents currency }
        createdAt
      }
    }
  }
}"""


class LedgerUnverified(ValueError):
    """External response is absent, malformed or cannot substantiate a fact."""


@dataclass(frozen=True)
class LedgerSnapshot:
    account_slug: str
    source_url: str
    retrieved_at: datetime
    transaction_count: int
    sample_credit_cents: int
    sample_debit_cents: int
    currencies: tuple[str,...]
    snapshot_sha256: str
    proof_level: str="P0"
    verified_beneficiary_impact: None=None


class OpenCollectivePublicLedger:
    def __init__(self, *, opener=None):
        self._open=opener if opener is not None else urlopen

    def read(self, account_slug: str, *, at:datetime) -> LedgerSnapshot:
        if (not isinstance(account_slug,str) or
            not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}",account_slug)):
            raise ValueError("public collective slug must be 2..64 lowercase characters")
        if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware readback time required")
        payload=json.dumps({"query":QUERY,"variables":{"slug":account_slug}},separators=(",",":")).encode()
        req=Request(ENDPOINT,data=payload,headers={
            "Content-Type":"application/json",
            "Accept":"application/json",
            "User-Agent":"Manager-Research-Public-ReadOnly/0.1"
        },method="POST")
        try:
            with self._open(req,timeout=12) as response:
                response_bytes=response.read(65537)
            if not isinstance(response_bytes,bytes) or len(response_bytes)>65536:
                raise LedgerUnverified("provider payload size exceeds bounded read")
            data=json.loads(response_bytes)
            if not isinstance(data,dict) or data.get("errors"):
                raise LedgerUnverified("provider GraphQL error")
            account=data["data"]["account"]
            if not isinstance(account,dict) or account.get("slug")!=account_slug:
                raise LedgerUnverified("mismatched provider account")
            transactions=account["transactions"]
            total=transactions["totalCount"]
            nodes=transactions["nodes"]
            if (type(total) is not int or total<0 or not isinstance(nodes,list)
                or len(nodes)>4 or total<len(nodes)):
                raise LedgerUnverified("invalid ledger count/sample")
            seen=set()
            credits=debits=0
            currencies=set()
            valid=[]
            for node in nodes:
                if not isinstance(node,dict):
                    raise LedgerUnverified("malformed transaction")
                opaque=node["id"]
                kind=node["kind"]
                direction=node["type"]
                money=node["amount"]
                time=node["createdAt"]
                if not isinstance(opaque,str) or not opaque or opaque in seen:
                    raise LedgerUnverified("duplicate or missing transaction identifier")
                seen.add(opaque)
                if (not isinstance(kind,str) or not re.fullmatch("[A-Z_]{2,60}",kind)
                    or direction not in ("CREDIT","DEBIT")):
                    raise LedgerUnverified("invalid public ledger transaction kind")
                cents=money["valueInCents"]
                currency=money["currency"]
                if (type(cents) is not int or not -10**15<cents<10**15
                    or not isinstance(currency,str) or not re.fullmatch("[A-Z]{3}",currency)):
                    raise LedgerUnverified("invalid amount/currency")
                if not isinstance(time,str):
                    raise LedgerUnverified("missing transaction time")
                parsed=datetime.fromisoformat(time.replace("Z","+00:00"))
                if parsed.tzinfo is None:
                    raise LedgerUnverified("timezone-free transaction is untrusted")
                currencies.add(currency)
                credits+=cents if direction=="CREDIT" else 0
                debits+=cents if direction=="DEBIT" else 0
                valid.append({"id":opaque,"kind":kind,"type":direction,
                              "cents":cents,"currency":currency,"time":parsed.isoformat()})
            # Do not sum monetary units of different currencies into one number.
            if len(currencies)>1:
                raise LedgerUnverified("mixed currencies must not be summed")
            snapshot_sha=sha256(json.dumps(valid,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            return LedgerSnapshot(account_slug,ENDPOINT,at,total,credits,debits,
                                  tuple(sorted(currencies)),snapshot_sha)
        except LedgerUnverified:
            raise
        except Exception:
            # Do not leak raw API body, private donor records or host exception.
            raise LedgerUnverified("public ledger readback UNKNOWN") from None
