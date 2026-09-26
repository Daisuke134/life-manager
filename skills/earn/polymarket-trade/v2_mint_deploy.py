#!/usr/bin/env python3
"""Mint Polymarket V2 RelayerApiKey via SIWE (no browser) -> deploy deposit wallet."""
import os
import requests
from eth_account import Account

KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY"); KEY = KEY if KEY.startswith("0x") else "0x"+KEY
acct = Account.from_key(KEY)
ADDR = acct.address
GAMMA = "https://gamma-api.polymarket.com"
RELAYER = "https://relayer-v2.polymarket.com"

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Origin": "https://polymarket.com", "Referer": "https://polymarket.com/"})

# 1-5. SIWE login (server challenge; shared with every relayer caller)
from relayer_auth import siwe_login
siwe_login(s, acct)
print("cookies:", [c.name for c in s.cookies])

# 6. POST relayer auth -> {apiKey, address}
r = s.post(f"{RELAYER}/relayer/api/auth", json={}, timeout=20)
print("relayer/auth HTTP", r.status_code, r.text[:200])
if r.status_code == 200:
    data = r.json()
    api_key = data.get("apiKey") or data.get("api_key")
    print("RELAYER API KEY:", api_key)
    # 7. deploy deposit wallet using RelayerApiKey
    from polymarket.clients.secure import SecureClient
    from polymarket.auth import RelayerApiKey
    tmp = SecureClient._create(private_key=KEY, validate_credentials=True)
    creds = tmp._ctx.credentials; dw = str(tmp._ctx.wallet); tmp.close()
    print("deposit wallet:", dw)
    rk = RelayerApiKey(key=api_key, address=ADDR)
    c = SecureClient.create(private_key=KEY, credentials=creds, api_key=rk)
    print("client ready. deploying / checking deposit wallet...")
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
    code = w3.eth.get_code(w3.to_checksum_address(dw))
    print("DEPOSIT WALLET DEPLOYED?:", "YES ✅ "+dw if len(code) > 2 else "still NO")
    c.close()
else:
    print("relayer auth failed — inspect body above")
