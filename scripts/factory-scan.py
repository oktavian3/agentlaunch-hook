#!/usr/bin/env python3
"""
AgentYield Factory Scanner + Bot Runner
Scans factory, runs bot on all alive agents with deposits.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

# Load .env
from dotenv import load_dotenv
load_dotenv('/root/agentlaunch-hook/.env')

from web3 import Web3

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "0x80bfBc37E3c17C407fd142cE6FB561EC421A7336")
CHAIN_ID = 196
OPERATOR = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

# ABIs
HOOK_ABI = json.loads(json.dumps([
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
    {"inputs":[],"name":"autoCompound","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMessageCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"index","type":"uint256"}],"name":"getMessage","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getDepositorCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
]))

FACTORY_ABI = [
    {"inputs":[],"name":"getAgentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"","type":"uint256"}],"name":"agents","outputs":[{"name":"hookAddress","type":"address"},{"name":"owner","type":"address"},{"name":"name","type":"string"},{"name":"mode","type":"uint8"},{"name":"createdAt","type":"uint256"}],"stateMutability":"view","type":"function"},
]

w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    print("ERROR: Cannot connect to X Layer")
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
wallet = account.address

print("=" * 70)
print(f"🤖 AGENTYIELD FACTORY SCAN BOT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 70)
print(f"Operator wallet: {wallet}")
print(f"Factory:         {FACTORY_ADDRESS}")
print(f"RPC:             {RPC}")
print()

factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
agent_count = factory.functions.getAgentCount().call()
print(f"📊 Total agents in factory: {agent_count}")
print()

# ── Scan all agents ──
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
        print(f"  Agent #{i}: {name[:40]:40s} | hook={hook_addr[:10]}.. | owner={owner[:10]}.. | mode={mode}")
    except Exception as e:
        print(f"  Agent #{i}: Error reading — {e}")

print()

# ── Connect to each agent and get info ──
MODES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}

agents_with_tvl = []
operator_agents = []
total_tvl = 0
nonce = w3.eth.get_transaction_count(wallet)
gas_price = w3.eth.gas_price

for agent in all_agents:
    hook_addr = agent["hook"]
    try:
        hook = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)
        info = hook.functions.getAgentInfo().call()
        tvl = info[2]
        alive = info[10]
        treasury = info[3]
        depositor_count = info[5]
        mode_val = info[7]

        tvl_eth = float(w3.from_wei(tvl, 'ether'))
        total_tvl += tvl_eth

        status = "🟢 Alive" if alive else "🔴 Dead"
        print(f"  {agent['name'][:35]:35s} | TVL={tvl_eth:.4f} ETH | {status} | Dep={depositor_count} | Mode={MODES.get(mode_val, '?')}")

        if alive and tvl > 0:
            agents_with_tvl.append({
                "agent": agent,
                "hook": hook,
                "info": info,
                "tvl_eth": tvl_eth,
            })

        # Check if owned by operator
        if agent["owner"].lower() == OPERATOR.lower():
            operator_agents.append({
                "agent": agent,
                "hook": hook,
                "info": info,
                "tvl_eth": tvl_eth,
            })

    except Exception as e:
        print(f"  {agent['name'][:35]:35s} | Error reading info: {e}")

print()
print(f"📊 Total TVL across all agents: {total_tvl:.4f} ETH")
print(f"📊 Agents alive with TVL > 0: {len(agents_with_tvl)}")
print(f"📊 Agents owned by operator: {len(operator_agents)}")
print()

# ── Phase 2: Run simulateSwapFee on all agents with deposits ──
if agents_with_tvl:
    print("=" * 70)
    print("⚡ EXECUTING simulateSwapFee ON ALL AGENTS WITH DEPOSITS")
    print("=" * 70)
    
    for entry in agents_with_tvl:
        agent = entry["agent"]
        hook = entry["hook"]
        info = entry["info"]
        tvl_eth = entry["tvl_eth"]
        tvl_wei = info[2]
        treasury = info[3]
        
        print(f"\n  🔷 Agent: {agent['name']} (hook={agent['hook'][:10]}..)")
        print(f"     TVL: {tvl_eth:.4f} ETH")
        
        # Simulate ~0.1% of TVL as swap fee per cycle
        sim_amount = int(tvl_wei * 0.001)
        if sim_amount < 1:
            sim_amount = int(tvl_wei * 0.0001)  # try 0.01%
        if sim_amount < 1:
            sim_amount = 1  # minimum 1 wei
        
        print(f"     Simulating swap fee: {w3.from_wei(sim_amount, 'ether'):.10f} ETH")
        
        try:
            tx = hook.functions.simulateSwapFee(sim_amount).build_transaction({
                'from': wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            print(f"     ✅ simulateSwapFee succeeded! TX: {tx_hash.hex()}")
            nonce += 1
        except Exception as e:
            print(f"     ❌ simulateSwapFee failed: {e}")
        
        # Small delay between txs
        time.sleep(0.5)
    
    print()
else:
    print("⚠️ No agents with deposits found — skipping simulateSwapFee.")
    print()

# ── Phase 3: Post status for operator-owned agents ──
if operator_agents:
    print("=" * 70)
    print("📝 POSTING STATUS MESSAGES FOR OPERATOR-OWNED AGENTS")
    print("=" * 70)
    
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    
    for entry in operator_agents:
        agent = entry["agent"]
        hook = entry["hook"]
        info = entry["info"]
        tvl_eth = entry["tvl_eth"]
        mode_val = info[7]
        
        print(f"\n  🔷 Agent: {agent['name']} (owner match)")
        
        try:
            apy = hook.functions.estimatedAPY().call()
            apy_pct = apy / 100
            treasury_eth = float(w3.from_wei(info[3], 'ether'))
            depositors = info[5]
            
            mode_name = MODES.get(mode_val, "Balanced")
            
            msg = f"🤖 AgentYield | {ts} | TVL: {tvl_eth:.4f} ETH | APY: {apy_pct:.2f}% | Mode: {mode_name} | Treasury: {treasury_eth:.6f} ETH | Depositors: {depositors}"
            
            tx = hook.functions.postMessage(msg).build_transaction({
                'from': wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            print(f"     ✅ Status posted! TX: {tx_hash.hex()}")
            nonce += 1
        except Exception as e:
            print(f"     ❌ Post failed: {e}")
        
        time.sleep(0.5)
    
    print()
else:
    print("⚠️ No operator-owned agents found — skipping status posts.")
    print()

# Also run the bot for the specific agent: 0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b
print("=" * 70)
print("🎯 RUNNING DEDICATED BOT FOR SPECIFIED AGENT")
print("=" * 70)
print(f"Agent: 0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b")
print()

# Import and run the standard bot script for this agent
hook_addr_check = "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"

try:
    hook = w3.eth.contract(address=Web3.to_checksum_address(hook_addr_check), abi=HOOK_ABI)
    info = hook.functions.getAgentInfo().call()
    
    tvl = info[2]
    alive = info[10]
    tvl_eth = float(w3.from_wei(tvl, 'ether'))
    name = info[0]
    
    print(f"  Name: {name}")
    print(f"  TVL: {tvl_eth:.4f} ETH")
    print(f"  Alive: {alive}")
    print(f"  Depositors: {info[5]}")
    
    if alive and tvl > 0:
        # Simulate fee
        sim_amount = max(int(tvl * 0.001), 1)
        print(f"\n  💸 Simulating fee: {w3.from_wei(sim_amount, 'ether'):.6f} ETH")
        
        try:
            tx = hook.functions.simulateSwapFee(sim_amount).build_transaction({
                'from': wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            print(f"  ✅ TX: {tx_hash.hex()}")
            nonce += 1
        except Exception as e:
            print(f"  ❌ {e}")
        
        # Read treasury and try reinvest
        treasury_wei = info[3]
        if treasury_wei > w3.to_wei(0.001, 'ether'):
            print(f"\n  💸 Treasury: {w3.from_wei(treasury_wei, 'ether'):.6f} ETH — attempting reinvest")
            try:
                tx = hook.functions.reinvest().build_transaction({
                    'from': wallet,
                    'nonce': nonce,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'chainId': CHAIN_ID,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                print(f"  ✅ Reinvest TX: {tx_hash.hex()}")
                nonce += 1
            except Exception as e:
                print(f"  ❌ Reinvest failed: {e}")
        
        # Post status message
        apy = hook.functions.estimatedAPY().call()
        apy_pct = apy / 100
        treasury_eth = float(w3.from_wei(info[3], 'ether'))
        depositors = info[5]
        mode_val = info[7]
        mode_name = MODES.get(mode_val, "Balanced")
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        
        msg = f"🤖 AgentYield Bot | {ts} | TVL: {tvl_eth:.4f} ETH | APY: {apy_pct:.2f}% | Mode: {mode_name} | Treasury: {treasury_eth:.6f} ETH | Depositors: {depositors}"
        
        print(f"\n  📝 Posting status message...")
        try:
            tx = hook.functions.postMessage(msg).build_transaction({
                'from': wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            print(f"  ✅ Status TX: {tx_hash.hex()}")
            nonce += 1
        except Exception as e:
            print(f"  ❌ Post failed: {e}")
    else:
        print(f"  ⚠️ Agent {'dead' if not alive else 'has no deposits'} — skipping actions")
except Exception as e:
    print(f"  ❌ Error processing agent: {e}")

print()
print("=" * 70)
print("✅ FACTORY SCAN BOT COMPLETE")
print("=" * 70)
