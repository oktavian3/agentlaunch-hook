#!/usr/bin/env python3
"""
AgentYield Full Bot Cycle — scans factory, runs simulateSwapFee -> autoCompound -> postMessage
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('/root/agentlaunch-hook/.env')
from web3 import Web3

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "0x80bfBc37E3c17C407fd142cE6FB561EC421A7336")
CHAIN_ID = 196
OPERATOR = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

HOOK_ABI = json.loads(json.dumps([
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"amount","type":"uint256"}],"name":"simulateSwapFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"autoCompound","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"reinvest","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"estimatedAPY","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
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
print(f"AGENTYIELD FULL BOT CYCLE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 70)
print(f"Operator: {wallet}")
print(f"Factory:  {FACTORY_ADDRESS}")
print()

# Scan factory
factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
agent_count = factory.functions.getAgentCount().call()
print(f"Agents in factory: {agent_count}")

all_agents = []
for i in range(agent_count):
    try:
        agent_data = factory.functions.agents(i).call()
        hook_addr = agent_data[0]
        owner = agent_data[1]
        name = agent_data[2]
        mode = agent_data[3]
        all_agents.append({"index": i, "hook": hook_addr, "owner": owner, "name": name, "mode": mode})
        print(f"  Agent #{i}: {name} | hook={hook_addr} | owner={owner[:10]}.. | mode={mode}")
    except Exception as e:
        print(f"  Agent #{i}: Error — {e}")

print()

# Also include TestAgent02 (pre-existing named agent)
TEST_AGENT = "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"
all_hook_addresses = [a["hook"] for a in all_agents]
if TEST_AGENT.lower() not in [h.lower() for h in all_hook_addresses]:
    print(f"Also including TestAgent02 ({TEST_AGENT})")
    # Check if alive by trying getAgentInfo
    try:
        hook = w3.eth.contract(address=Web3.to_checksum_address(TEST_AGENT), abi=HOOK_ABI)
        info = hook.functions.getAgentInfo().call()
        print(f"  TestAgent02: TVL={float(w3.from_wei(info[2], 'ether')):.6f} ETH | Alive={info[10]}")
        agents_to_process = all_agents + [{"index": -1, "hook": TEST_AGENT, "owner": "", "name": "TestAgent02", "mode": info[7]}]
    except Exception as e:
        print(f"  TestAgent02 error: {e}")
        agents_to_process = all_agents
else:
    agents_to_process = all_agents

nonce = w3.eth.get_transaction_count(wallet)
gas_price = w3.eth.gas_price
print(f"Nonce: {nonce} | Gas price: {gas_price}")
print()

# Process each agent
MODES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}

for agent in agents_to_process:
    hook_addr = agent["hook"]
    agent_name = agent["name"]
    
    print("-" * 60)
    print(f"Processing: {agent_name}")
    print(f"  Hook: {hook_addr}")
    
    try:
        hook = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)
        info = hook.functions.getAgentInfo().call()
    except Exception as e:
        print(f"  SKIP — cannot read agent info: {str(e)[:80]}")
        continue
    
    tvl = info[2]
    treasury = info[3]
    alive = info[10]
    
    tvl_eth = float(w3.from_wei(tvl, 'ether'))
    treasury_eth = float(w3.from_wei(treasury, 'ether'))
    
    print(f"  Alive: {alive} | TVL: {tvl_eth:.6f} ETH | Treasury: {treasury_eth:.6f} ETH")
    
    if not alive or tvl == 0:
        print("  SKIP — not alive or no deposits")
        continue
    
    # Step 1: simulateSwapFee
    sim_amount = max(int(tvl * 0.001), 1)
    print(f"  1. simulateSwapFee({w3.from_wei(sim_amount, 'ether'):.10f} ETH)")
    
    try:
        tx = hook.functions.simulateSwapFee(sim_amount).build_transaction({
            'from': wallet, 'nonce': nonce, 'gas': 150000,
            'gasPrice': gas_price, 'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        print(f"     TX: {tx_hash.hex()}")
        nonce += 1
        time.sleep(0.5)
    except Exception as e:
        print(f"     FAILED: {str(e)[:100]}")
    
    # Step 2: autoCompound
    # Re-read info for fresh treasury
    try:
        info = hook.functions.getAgentInfo().call()
        treasury = info[3]
        treasury_eth = float(w3.from_wei(treasury, 'ether'))
    except:
        pass
    
    print(f"  Treasury after simulate: {treasury_eth:.6f} ETH")
    
    if treasury > 0:
        print(f"  2. autoCompound()")
        auto_succeeded = False
        try:
            tx = hook.functions.autoCompound().build_transaction({
                'from': wallet, 'nonce': nonce, 'gas': 300000,
                'gasPrice': gas_price, 'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            status = receipt['status']
            print(f"     TX: {tx_hash.hex()} status={status}")
            if status == 1:
                auto_succeeded = True
            else:
                print(f"     WARN: autoCompound returned status=0 — trying reinvest fallback")
            nonce += 1
            time.sleep(0.5)
        except Exception as e:
            err = str(e)
            print(f"     autoCompound exception: {err[:100]}")
            if 'cooldown' in err.lower():
                print(f"     Cooldown detected")
        
        if not auto_succeeded:
            try:
                info = hook.functions.getAgentInfo().call()
                if info[3] > 0:
                    print(f"     Fallback: reinvest() — treasury={w3.from_wei(info[3], 'ether'):.6f} ETH")
                    tx = hook.functions.reinvest().build_transaction({
                        'from': wallet, 'nonce': nonce, 'gas': 300000,
                        'gasPrice': gas_price, 'chainId': CHAIN_ID,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    print(f"     reinvest TX: {tx_hash.hex()} status={receipt['status']}")
                    nonce += 1
                    time.sleep(0.5)
                else:
                    print(f"     Fallback skipped — treasury empty")
            except Exception as e2:
                print(f"     reinvest also failed: {str(e2)[:100]}")
    else:
        print(f"  2. autoCompound — skipped (treasury=0)")
    
    # Step 3: postMessage (for operator-owned agents)
    is_operator = agent.get("owner", "").lower() == OPERATOR.lower() or agent_name == "AutoYieldAgent"
    
    if is_operator:
        print(f"  3. postMessage()")
        try:
            info = hook.functions.getAgentInfo().call()
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            tvl_now = float(w3.from_wei(info[2], 'ether'))
            treasury_now = float(w3.from_wei(info[3], 'ether'))
            depositors = info[5]
            mode_name = MODES.get(info[7], 'Balanced')
            
            # Short message to avoid v5 proxy postMessage compatibility issues
            msg = f"AgentYield {ts} TVL:{tvl_now:.4f}ETH Mode:{mode_name} Treasury:{treasury_now:.6f}ETH Depositors:{depositors}"
            
            tx = hook.functions.postMessage(msg).build_transaction({
                'from': wallet, 'nonce': nonce, 'gas': 150000,
                'gasPrice': gas_price, 'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            status = receipt['status']
            print(f"     TX: {tx_hash.hex()} status={status}")
            if status == 0:
                # Try shorter message without depositors
                msg2 = f"AgentYield {ts} TVL:{tvl_now:.4f}ETH Treasury:{treasury_now:.6f}ETH"
                print(f"     Retry with shorter message...")
                tx2 = hook.functions.postMessage(msg2).build_transaction({
                    'from': wallet, 'nonce': nonce + 1, 'gas': 150000,
                    'gasPrice': gas_price, 'chainId': CHAIN_ID,
                })
                signed2 = account.sign_transaction(tx2)
                tx_hash2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
                receipt2 = w3.eth.wait_for_transaction_receipt(tx_hash2, timeout=120)
                print(f"     Retry TX: {tx_hash2.hex()} status={receipt2['status']}")
                nonce += 2
            else:
                nonce += 1
        except Exception as e:
            print(f"     FAILED: {str(e)[:100]}")

print()
print("=" * 70)
print("BOT CYCLE COMPLETE")
print("=" * 70)
