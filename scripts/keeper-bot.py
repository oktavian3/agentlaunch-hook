#!/usr/bin/env python3
"""
SoulAgent Keeper Bot — Autonomous AI Agent Heartbeat & On-Chain Interaction
============================================================================
This script runs periodically (cron job, every 6h) and:
1. Sends a heartbeat() to the SoulAgent Hook — proves the agent is alive
2. Posts an on-chain message — "Agent status: operational"
3. Checks and reports treasury balance
4. Optionally adjusts fee based on time-of-day logic

Think of this as the AI agent's pulse — if this stops, the agent is dead.

Usage:
  export PRIVATE_KEY=0x...
  python3 keeper-bot.py

Or via cron job (no_agent mode):
  cronjob(action='create', no_agent=True, script='scripts/keeper-bot.sh', schedule='0 */6 * * *')
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

# === CONFIG ===
RPC = "https://rpc.xlayer.tech"
HOOK_ADDRESS = "0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749"
CHAIN_ID = 196

# AgentHook ABI (minimal for our calls)
AGENT_ABI = json.dumps([
    {"inputs":[],"name":"heartbeat","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_newFee","type":"uint24"}],"name":"setFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"treasuryBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalFeesCollected","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[
        {"name":"wallet","type":"address"},
        {"name":"name","type":"string"},
        {"name":"description","type":"string"},
        {"name":"fee","type":"uint24"},
        {"name":"created","type":"uint40"},
        {"name":"lastSeen","type":"uint40"},
        {"name":"treasury","type":"uint256"},
        {"name":"totalFees","type":"uint256"},
        {"name":"messageCount","type":"uint256"},
        {"name":"agentPoolId","type":"bytes32"},
        {"name":"isAlive","type":"bool"}
    ],"stateMutability":"view","type":"function"}
])

def run():
    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        print("ERROR: PRIVATE_KEY not set")
        sys.exit(1)

    # Import web3
    try:
        from web3 import Web3
    except ImportError:
        print("ERROR: web3.py not installed. Run: pip install web3")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to {RPC}")
        sys.exit(1)

    account = w3.eth.account.from_key(pk)
    agent_wallet = account.address
    contract = w3.eth.contract(address=HOOK_ADDRESS, abi=json.loads(AGENT_ABI))

    print(f"🤖 SoulAgent Keeper Bot")
    print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"   Agent Wallet: {agent_wallet}")
    print(f"   Hook Address: {HOOK_ADDRESS}")
    print()

    # 1. Read current state
    try:
        info = contract.functions.getAgentInfo().call()
        print(f"📊 Agent State:")
        print(f"   Name:     {info[1]}")
        print(f"   Fee:      {info[3]} bps ({info[3]/100:.2f}%)")
        print(f"   Created:  {datetime.fromtimestamp(info[4], tz=timezone.utc).strftime('%Y-%m-%d')}")
        print(f"   Last Seen: {datetime.fromtimestamp(info[5], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"   Treasury: {w3.from_wei(info[6], 'ether')} ETH")
        print(f"   Total Fees: {w3.from_wei(info[7], 'ether')} ETH")
        print(f"   Messages: {info[8]}")
        print(f"   Alive:    {'✅ YES' if info[10] else '❌ NO'}")
    except Exception as e:
        print(f"ERROR reading state: {e}")
        sys.exit(1)

    print()

    # 2. Send heartbeat
    print(f"💓 Sending heartbeat...")
    try:
        tx = contract.functions.heartbeat().build_transaction({
            'from': agent_wallet,
            'nonce': w3.eth.get_transaction_count(agent_wallet),
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"   ✅ Heartbeat sent! TX: {tx_hash.hex()}")
        print(f"   Gas used: {receipt['gasUsed']}")
    except Exception as e:
        print(f"   ❌ Heartbeat failed: {e}")

    # 3. Post on-chain message
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    msg = f"SoulAgent operational at {ts} | treasury: {w3.from_wei(contract.functions.treasuryBalance().call(), 'ether'):.6f} ETH | fee: {contract.functions.getAgentInfo().call()[3]/100:.2f}%"
    print(f"\n📝 Posting message: \"{msg}\"")
    try:
        tx = contract.functions.postMessage(msg).build_transaction({
            'from': agent_wallet,
            'nonce': w3.eth.get_transaction_count(agent_wallet),
            'gas': 150000,
            'gasPrice': w3.eth.gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"   ✅ Message posted! TX: {tx_hash.hex()}")
        print(f"   Gas used: {receipt['gasUsed']}")
    except Exception as e:
        print(f"   ❌ Message failed: {e}")

    # 4. Summary
    print()
    print(f"✅ Keeper bot run complete.")
    print(f"   Explorer: https://www.okx.com/explorer/xlayer/address/{HOOK_ADDRESS}")

if __name__ == "__main__":
    run()
