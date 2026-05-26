#!/usr/bin/env python3
"""
AgentYield Factory Scan Bot
Scans the factory for all agents, processes those with TVL > 0.
Also handles the specific --agent for targeted runs.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/agentlaunch-hook/.env')

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "0x74A25c7831EB3EC76402392fD394eEd31F218BCB")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

CHAIN_ID = 196
OPERATOR_WALLET = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

HOOK_ABI = json.dumps([
    {"inputs":[],"name":"agentName","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"agentWallet","outputs":[{"name":"","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"treasuryBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalDeposits","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalFeesCollected","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastReinvestTime","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"REINVEST_COOLDOWN","outputs":[{"name":"","type":"uint32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"reinvest","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_newFee","type":"uint24"}],"name":"setFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_newMode","type":"uint8"}],"name":"setMode","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_newLower","type":"int24"},{"name":"_newUpper","type":"int24"}],"name":"rebalancePosition","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"estimatedAPY","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"amount","type":"uint256"}],"name":"simulateSwapFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMessageCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"index","type":"uint256"}],"name":"getMessage","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getDepositorCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
])

FACTORY_ABI = json.dumps([
    {"inputs":[],"name":"getAgentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"","type":"uint256"}],"name":"agents","outputs":[{"name":"hookAddress","type":"address"},{"name":"owner","type":"address"},{"name":"name","type":"string"},{"name":"mode","type":"uint8"},{"name":"createdAt","type":"uint256"}],"stateMutability":"view","type":"function"},
])

MODES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}

from web3 import Web3

w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    print(f"❌ ERROR: Cannot connect to {RPC}")
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
wallet = account.address
print(f"🔌 Connected to X Layer (Chain ID: {CHAIN_ID})")
print(f"👛 Operator wallet: {wallet}")
print(f"   (matches expected: {wallet.lower() == OPERATOR_WALLET.lower()})")

factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=json.loads(FACTORY_ABI))

ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

def get_contract(addr):
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=json.loads(HOOK_ABI))

def simulate_fee(hook_contract, amount_wei, nonce, gas_price):
    try:
        tx = hook_contract.functions.simulateSwapFee(amount_wei).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 150000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex(), receipt['gasUsed']
    except Exception as e:
        return None, str(e)

def post_message(hook_contract, msg, nonce, gas_price):
    try:
        tx = hook_contract.functions.postMessage(msg).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 150000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex(), receipt['gasUsed']
    except Exception as e:
        return None, str(e)

# ============================================================
# PHASE 1: Run the specific agent bot first
# ============================================================
print(f"\n{'='*60}")
print(f"📌 PHASE 1: Specific Agent Bot")
print(f"{'='*60}")

target_agent = "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"
print(f"\n🎯 Running bot for agent: {target_agent}")
hook = get_contract(target_agent)

# Read state
try:
    info = hook.functions.getAgentInfo().call()
    state = {
        "name": info[0],
        "wallet": info[1],
        "tvl_eth": float(w3.from_wei(info[2], 'ether')),
        "treasury_eth": float(w3.from_wei(info[3], 'ether')),
        "total_fees_eth": float(w3.from_wei(info[4], 'ether')),
        "depositor_count": info[5],
        "msg_count": info[6],
        "mode": info[7],
        "fee_bps": info[8],
        "liquidity": info[9],
        "alive": info[10],
    }
    state["fee_pct"] = state["fee_bps"] / 100
    try:
        state["apy_bps"] = hook.functions.estimatedAPY().call()
        state["apy_pct"] = state["apy_bps"] / 100
    except:
        state["apy_bps"] = 0
        state["apy_pct"] = 0.0

    print(f"  Name:       {state['name']}")
    print(f"  Mode:       {MODES.get(state['mode'], '?')} (mode={state['mode']})")
    print(f"  Fee:        {state['fee_pct']:.2f}%")
    print(f"  TVL:        {state['tvl_eth']:.4f} ETH")
    print(f"  Treasury:   {state['treasury_eth']:.6f} ETH")
    print(f"  Total Fees: {state['total_fees_eth']:.6f} ETH")
    print(f"  Depositors: {state['depositor_count']}")
    print(f"  APY:        {state['apy_pct']:.2f}%")
    print(f"  Alive:      {state['alive']}")
    print(f"  Msg Count:  {state['msg_count']}")
except Exception as e:
    print(f"  ❌ Error reading agent state: {e}")
    state = {}

# Decide & Execute
target_actions = []
target_state = {}
if state and state.get("alive", False):
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    # Simulate fee if TVL > 0
    if state.get("tvl_eth", 0) > 0:
        sim_amount = int(state["tvl_eth"] * 0.001 * 1e18)
        if sim_amount > 0:
            print(f"\n  💸 Simulating swap fee: {w3.from_wei(sim_amount, 'ether'):.6f} ETH ...")
            tx_hash, result = simulate_fee(hook, sim_amount, nonce, gas_price)
            if tx_hash:
                print(f"     ✅ TX: {tx_hash} (gas: {result})")
                target_actions.append(f"simulateSwapFee({w3.from_wei(sim_amount, 'ether'):.6f} ETH) → {tx_hash}")
                nonce += 1
            else:
                print(f"     ❌ Failed: {result}")

    # Post status message (operator wallet owns it)
    print(f"\n  📝 Posting on-chain status message ...")
    mode_name = MODES.get(state.get("mode", 1), "Balanced")
    msg = f"🤖 AgentYield Bot | {ts} | TVL: {state['tvl_eth']:.4f} ETH | APY: {state['apy_pct']:.2f}% | Mode: {mode_name} | Treasury: {state['treasury_eth']:.6f} ETH | Depositors: {state['depositor_count']}"
    tx_hash, result = post_message(hook, msg, nonce, gas_price)
    if tx_hash:
        print(f"     ✅ TX: {tx_hash} (gas: {result})")
        target_actions.append(f"postMessage() → {tx_hash}")
    else:
        print(f"     ❌ Failed: {result}")

    target_state = state
else:
    print(f"  ⚠️ Agent not alive or no state, skipping actions")

# ============================================================
# PHASE 2: Scan factory for ALL agents
# ============================================================
print(f"\n{'='*60}")
print(f"🔍 PHASE 2: Factory Scan — All Agents")
print(f"{'='*60}")

try:
    agent_count = factory.functions.getAgentCount().call()
    print(f"\n📊 Total agents in factory: {agent_count}")
except Exception as e:
    print(f"❌ Error getting agent count: {e}")
    agent_count = 0

all_agents = []

for i in range(agent_count):
    try:
        agent_data = factory.functions.agents(i).call()
        hook_addr = agent_data[0]
        owner = agent_data[1]
        name = agent_data[2]
        mode = agent_data[3]
        created_at = agent_data[4]

        all_agents.append({
            "index": i,
            "hook": hook_addr,
            "owner": owner,
            "name": name,
            "mode": mode,
            "created_at": created_at,
        })
        print(f"\n  [{i}] {name}")
        print(f"      Hook:  {hook_addr}")
        print(f"      Owner: {owner}")
        print(f"      Mode:  {MODES.get(mode, '?')}")
    except Exception as e:
        print(f"\n  [{i}] Error reading agent: {e}")

# ============================================================
# PHASE 3: For each agent with TVL > 0 and alive, call simulateSwapFee
# Also post status for operator-owned agents
# ============================================================
print(f"\n{'='*60}")
print(f"⚡ PHASE 3: Process Live Agents (TVL > 0 & Alive)")
print(f"{'='*60}")

nonce = w3.eth.get_transaction_count(wallet)
gas_price = w3.eth.gas_price
print(f"  Nonce start: {nonce} | Gas price: {gas_price} wei")

scanned = []
total_tvl = 0.0
total_fees_simulated = 0
total_msgs_posted = 0
failed_agents = []

for agent in all_agents:
    try:
        hook_contract = get_contract(agent["hook"])
        info = hook_contract.functions.getAgentInfo().call()
        tvl_eth = float(w3.from_wei(info[2], 'ether'))
        alive = info[10]
        agent_name = info[0]
        depositors = info[5]
        treasury_eth = float(w3.from_wei(info[3], 'ether'))
        apy = 0
        try:
            apy = hook_contract.functions.estimatedAPY().call() / 100
        except:
            pass

        print(f"\n  [{agent['index']}] {agent_name}")
        print(f"      TVL: {tvl_eth:.4f} ETH | Alive: {alive} | Treasury: {treasury_eth:.6f} ETH")
        print(f"      Depositors: {depositors} | APY: {apy:.2f}%")

        is_operator = agent["owner"].lower() == OPERATOR_WALLET.lower()
        print(f"      Operator-owned: {'YES' if is_operator else 'no'}")

        if alive and tvl_eth > 0:
            total_tvl += tvl_eth
            sim_amount = int(tvl_eth * 0.001 * 1e18)
            if sim_amount > 0:
                print(f"      💸 simulateSwapFee({w3.from_wei(sim_amount, 'ether'):.6f} ETH) ...", end=" ")
                tx_hash, result = simulate_fee(hook_contract, sim_amount, nonce, gas_price)
                if tx_hash:
                    print(f"✅ TX: {tx_hash[:20]}... gas: {result}")
                    total_fees_simulated += 1
                    scanned.append({
                        "agent": agent_name,
                        "hook": agent["hook"],
                        "action": "simulateSwapFee",
                        "amount_eth": w3.from_wei(sim_amount, 'ether'),
                        "tx": tx_hash,
                    })
                    nonce += 1
                else:
                    print(f"❌ {result}")
                    failed_agents.append(f"{agent_name}: simulateFee → {result}")

            # Post status if operator-owned
            if is_operator:
                mode_name = MODES.get(agent["mode"], "Balanced")
                msg = f"🤖 AgentYield Bot | {ts} | {agent_name} | TVL: {tvl_eth:.4f} ETH | APY: {apy:.2f}% | Mode: {mode_name} | Treasury: {treasury_eth:.6f} ETH | Depositors: {depositors}"
                print(f"      📝 postMessage() ...", end=" ")
                tx_hash, result = post_message(hook_contract, msg, nonce, gas_price)
                if tx_hash:
                    print(f"✅ TX: {tx_hash[:20]}... gas: {result}")
                    total_msgs_posted += 1
                    scanned.append({
                        "agent": agent_name,
                        "hook": agent["hook"],
                        "action": "postMessage",
                        "tx": tx_hash,
                    })
                    nonce += 1
                else:
                    print(f"❌ {result}")
                    failed_agents.append(f"{agent_name}: postMessage → {result}")
        else:
            if not alive:
                print(f"      ⏭️ Skipped: not alive")
            else:
                print(f"      ⏭️ Skipped: TVL = 0")

    except Exception as e:
        print(f"      ❌ Error: {e}")
        failed_agents.append(f"{agent['name']}: {str(e)[:80]}")

# ============================================================
# SUMMARY
# ============================================================
print(f"\n{'='*60}")
print(f"📋 FINAL SUMMARY — AgentYield Factory Bot")
print(f"{'='*60}")
print(f"  Timestamp:      {ts}")
print(f"  Operator:       {wallet}")
print(f"  Factory:        {FACTORY_ADDRESS}")
print(f"  Total agents:   {agent_count}")
print(f"  Total TVL:      {total_tvl:.4f} ETH")

if target_actions:
    print(f"\n  📍 Target Agent ({target_agent}):")
    for a in target_actions:
        print(f"     ✅ {a}")

print(f"\n  📊 Factory Scan Actions:")
print(f"     ✅ simulateSwapFee: {total_fees_simulated} agent(s)")
print(f"     ✅ postMessage:     {total_msgs_posted} agent(s)")

if scanned:
    print(f"\n  📋 Detailed Actions:")
    for s in scanned:
        if s["action"] == "simulateSwapFee":
            print(f"     💸 {s['agent']}: simulateSwapFee({s['amount_eth']:.6f} ETH) → {s['tx'][:20]}...")
        elif s["action"] == "postMessage":
            print(f"     📝 {s['agent']}: postMessage() → {s['tx'][:20]}...")

if failed_agents:
    print(f"\n  ❌ Failures ({len(failed_agents)}):")
    for f in failed_agents:
        print(f"     ⚠️ {f}")

print(f"\n{'='*60}")
print(f"✅ Bot cycle complete — {ts}")
print(f"{'='*60}")
