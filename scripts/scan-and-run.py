#!/usr/bin/env python3
"""
AgentYield Factory Scanner — scan ALL agents, run bot for active ones.
"""
import os
import json
import sys
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
CHAIN_ID = 196
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "")
PK = os.getenv("PRIVATE_KEY", "")
OPERATOR = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

from web3 import Web3

w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    print("❌ Cannot connect to X Layer RPC")
    sys.exit(1)

print(f"✅ Connected to X Layer (chain ID: {w3.eth.chain_id})")
account = w3.eth.account.from_key(PK)
wallet = account.address
print(f"💼 Operator wallet: {wallet}")
print(f"🏭 Factory: {FACTORY_ADDRESS}")

# ABIs
HOOK_ABI = [
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
]

FACTORY_ABI = [
    {"inputs":[],"name":"getAgentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"","type":"uint256"}],"name":"agents","outputs":[{"name":"hookAddress","type":"address"},{"name":"owner","type":"address"},{"name":"name","type":"string"},{"name":"mode","type":"uint8"},{"name":"createdAt","type":"uint256"}],"stateMutability":"view","type":"function"},
]

factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)

# ── Step 1: Read ALL agents from factory ──
print("\n" + "=" * 60)
print("📋 1. SCANNING FACTORY FOR ALL AGENTS")
print("=" * 60)

agent_count = factory.functions.getAgentCount().call()
print(f"Total agents in factory: {agent_count}")

all_agents = []
for i in range(agent_count):
    try:
        hook_addr, owner, name, mode, created_at = factory.functions.agents(i).call()
        all_agents.append({
            "index": i,
            "hook": hook_addr,
            "owner": owner.lower(),
            "name": name,
            "mode": mode,
            "created_at": created_at,
        })
        print(f"  [{i}] {name[:30]:30s} | Hook: {hook_addr[:10]}... | Owner: {owner[:10]}... | Mode: {mode}")
    except Exception as e:
        print(f"  [{i}] Error reading agent: {e}")

# ── Step 2: GetAgentInfo for each agent ──
print("\n" + "=" * 60)
print("🔍 2. READING AGENT INFO (TVL, alive, etc.)")
print("=" * 60)

active_agents = []
operator_agents = []

for agent in all_agents:
    try:
        hook_contract = w3.eth.contract(address=Web3.to_checksum_address(agent["hook"]), abi=HOOK_ABI)
        info = hook_contract.functions.getAgentInfo().call()
        # info = (name, wallet, tvl, treasury, totalFees, depositorCount, msgCount, mode, fee, liquidity, alive)
        agent_state = {
            "hook": agent["hook"],
            "owner": agent["owner"],
            "name": info[0],
            "wallet": info[1],
            "tvl_wei": info[2],
            "tvl_eth": float(w3.from_wei(info[2], 'ether')),
            "treasury_wei": info[3],
            "treasury_eth": float(w3.from_wei(info[3], 'ether')),
            "total_fees_eth": float(w3.from_wei(info[4], 'ether')),
            "depositor_count": info[5],
            "msg_count": info[6],
            "mode": info[7],
            "fee_bps": info[8],
            "liquidity": info[9],
            "alive": info[10],
        }

        # Get APY
        try:
            apy = hook_contract.functions.estimatedAPY().call()
            agent_state["apy_bps"] = apy
            agent_state["apy_pct"] = apy / 100
        except:
            agent_state["apy_pct"] = 0

        is_operator = agent["owner"] == OPERATOR.lower()

        status_icon = "✅" if agent_state["alive"] else "💀"
        owner_tag = " 👤 OPERATOR" if is_operator else ""
        print(f"  {status_icon} {agent_state['name'][:30]:30s} | TVL: {agent_state['tvl_eth']:.4f} ETH | Alive: {agent_state['alive']} | APY: {agent_state.get('apy_pct', 0):.2f}% | Depositors: {agent_state['depositor_count']}{owner_tag}")

        if agent_state["alive"] and agent_state["tvl_eth"] > 0:
            active_agents.append(agent_state)
        if is_operator:
            operator_agents.append(agent_state)

    except Exception as e:
        print(f"  ❌ Error reading {agent['hook'][:10]}...: {e}")

print(f"\n📊 Active agents (alive + TVL>0): {len(active_agents)}")
print(f"👤 Operator-owned agents: {len(operator_agents)}")

# ── Step 3: Run bot for the specific agent (0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b) ──
print("\n" + "=" * 60)
print("🤖 3. RUNNING BOT FOR 0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b")
print("=" * 60)

specific_hook = "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"
specific_contract = w3.eth.contract(address=Web3.to_checksum_address(specific_hook), abi=HOOK_ABI)

try:
    info = specific_contract.functions.getAgentInfo().call()
    print(f"  Name: {info[0]}")
    print(f"  TVL:  {w3.from_wei(info[2], 'ether'):.4f} ETH")
    print(f"  Alive: {info[10]}")

    if info[10] and info[2] > 0:
        # Simulate fee (~0.1% of TVL)
        sim_amount = int(info[2] * 0.001)
        print(f"  Simulating swap fee: {w3.from_wei(sim_amount, 'ether'):.6f} ETH")

        nonce = w3.eth.get_transaction_count(wallet)
        gas_price = w3.eth.gas_price

        tx = specific_contract.functions.simulateSwapFee(sim_amount).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 150000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"  ✅ simulateSwapFee executed — TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")

        # Post status
        nonce += 1
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        modes = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
        mode_name = modes.get(info[7], "Unknown")
        msg = f"🤖 AgentYield | {ts} | TVL: {w3.from_wei(info[2], 'ether'):.4f} ETH | APY: ?? | Mode: {mode_name} | Treasury: {w3.from_wei(info[3], 'ether'):.6f} ETH | Depositors: {info[5]}"

        tx2 = specific_contract.functions.postMessage(msg).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 150000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed2 = account.sign_transaction(tx2)
        tx_hash2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
        receipt2 = w3.eth.wait_for_transaction_receipt(tx_hash2)
        print(f"  ✅ Status posted — TX: {tx_hash2.hex()} (gas: {receipt2['gasUsed']})")
    else:
        print(f"  ⏭️ Agent not alive or TVL=0, skipping")

except Exception as e:
    print(f"  ❌ Error: {e}")

# ── Step 4: Simulate swap fees for ALL active agents ──
print("\n" + "=" * 60)
print("💸 4. SIMULATING SWAP FEES FOR ALL ACTIVE AGENTS")
print("=" * 60)

nonce = w3.eth.get_transaction_count(wallet)
gas_price = w3.eth.gas_price
sim_results = []

for agent in active_agents:
    hook_addr = agent["hook"]
    try:
        # Check if this agent's wallet is the operator or if we have permission
        # simulateSwapFee is permissionless (just generates fees)
        print(f"\n  Agent: {agent['name'][:30]:30s} | TVL: {agent['tvl_eth']:.4f} ETH")

        hook_contract = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)
        sim_amount = int(agent["tvl_wei"] * 0.001)
        if sim_amount == 0:
            print(f"    ⏭️ TVL too small for simulation")
            continue

        print(f"    Simulating {w3.from_wei(sim_amount, 'ether'):.6f} ETH fee swap...")
        tx = hook_contract.functions.simulateSwapFee(sim_amount).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 150000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        status = "✅ Success" if receipt['status'] == 1 else "❌ Failed"
        print(f"    {status} — TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
        sim_results.append({"agent": agent["name"], "hook": hook_addr, "tx": tx_hash.hex(), "status": "success" if receipt['status'] == 1 else "failed"})
        nonce += 1

        # Small delay between txs for safety
        time.sleep(0.5)

    except Exception as e:
        print(f"    ❌ Error: {e}")
        sim_results.append({"agent": agent["name"], "hook": hook_addr, "error": str(e)})

# ── Step 5: Post status for operator agents ──
print("\n" + "=" * 60)
print("📝 5. POSTING STATUS FOR OPERATOR-OWNED AGENTS")
print("=" * 60)

ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
post_results = []

for agent in operator_agents:
    hook_addr = agent["hook"]
    try:
        print(f"\n  Agent: {agent['name'][:30]:30s} | TVL: {agent['tvl_eth']:.4f} ETH")
        hook_contract = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)

        modes = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
        mode_name = modes.get(agent["mode"], "Unknown")
        msg = f"🔍 AgentYield Scan | {ts} | TVL: {agent['tvl_eth']:.4f} ETH | APY: {agent.get('apy_pct', 0):.2f}% | Mode: {mode_name} | Treasury: {agent['treasury_eth']:.6f} ETH | Depositors: {agent['depositor_count']} | Fees: {agent['total_fees_eth']:.6f} ETH"

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
        status = "✅ Posted" if receipt['status'] == 1 else "❌ Failed"
        print(f"    {status} — TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
        post_results.append({"agent": agent["name"], "hook": hook_addr, "tx": tx_hash.hex()})
        nonce += 1
    except Exception as e:
        print(f"    ❌ Error: {e}")


# ── FINAL SUMMARY ──
print("\n\n" + "=" * 60)
print("📊 FINAL SUMMARY")
print("=" * 60)
print(f"  Factory:          {FACTORY_ADDRESS}")
print(f"  Total agents:     {agent_count}")
print(f"  Alive + TVL>0:    {len(active_agents)}")
print(f"  Operator-owned:   {len(operator_agents)}")
print(f"  Wallet used:      {wallet}")
print(f"  Timestamp:        {ts}")
print()

if sim_results:
    print(f"  SimulateSwapFee calls:")
    for r in sim_results:
        status_icon = "✅" if r.get("status") == "success" else "❌"
        print(f"    {status_icon} {r['agent'][:30]:30s} | TX: {r.get('tx', 'ERROR')[:20]}...")
else:
    print(f"  No simulateSwapFee calls made (no agents with TVL>0)")

if post_results:
    print(f"  Status messages posted:")
    for r in post_results:
        print(f"    ✅ {r['agent'][:30]:30s} | TX: {r['tx'][:20]}...")
else:
    print(f"  No status messages posted")

print("=" * 60)
