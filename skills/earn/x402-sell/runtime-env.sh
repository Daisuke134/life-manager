#!/bin/bash

export X402_STATE_DIR="${X402_STATE_DIR:-${LIFE_MANAGER_STATE_ROOT:-$HOME/.local/state/life-manager/x402-sell}}"
mkdir -p "$X402_STATE_DIR"
