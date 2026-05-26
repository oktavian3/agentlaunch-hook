#!/usr/bin/env python3
"""
Factory-wide AgentYield bot scan — runs the bot for ALL agents in the factory.
Scans factory, finds all agents, processes each one.
"""
import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS")
OPERATOR = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"
CHAIN_ID = 196

from web3 import Web3
w3 = Web3(Web3.HTTPProvider(RPC))

if not w3.is_connected():
    print("FATAL: Cannot connect to X Layer RPC")
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
wallet = account.address

print("=" * 60)
print("🤖 AGENTYIELD FACTORY BOT — FULL FACTORY SCAN")
print("=" * 60)
print(f"Time:  {__import__('datetime').datetime.now()}")
print(f"RPC:   {RPC}")
print(f"Operator: {wallet}")
print()

# ── ABIs ──
FACTORY_ABI = json.loads(json.dumps([
    {"inputs":[],"name":"getAgentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"","type":"uint256"}],"name":"agents","outputs":[{"name":"hookAddress","type":"address"},{"name":"owner","type":"address"},{"name":"name","type":"string"},{"name":"mode","type":"uint8"},{"name":"createdAt","type":"uint256"}],"stateMutability":"view","type":"function"},
]))

HOOK_ABI = json.loads(json.dumps([
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"amount","type":"uint256"}],"name":"simulateSwapFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getMessageCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"index","type":"uint256"}],"name":"getMessage","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"estimatedAPY","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastReinvestTime","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"REINVEST_COOLDOWN","outputs":[{"name":"","type":"uint32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"reinvest","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"agentWallet","outputs":[{"name":"","type":"address"}],"stateMutability":"view","type":"function"},
]))

factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
count = factory.functions.getAgentCount().call()
print(f"📊 Total agents in factory: {count}")
print()

# ── Scan all agents ──
all_agents = []
for i in range(count):
    try:
        info = factory.functions.agents(i).call()
        all_agents.append({
            "index": i,
            "hook": info[0],
            "owner": info[1],
            "name": info[2],
            "mode": info[3],
            "created_at": info[4],
        })
        print(f"  [{i}] {info[2]:30s} owner={info[1][:10]}... hook={info[0][:10]}...")
    except Exception as e:
        print(f"  [{i}] ERROR reading agent: {e}")

print()
print("=" * 60)
print("📋 AGENT DETAILS")
print("=" * 60)

active_agents = []
for a in all_agents:
    hook_addr = a["hook"]
    try:
        hook = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)
        agent_info = hook.functions.getAgentInfo().call()
        tvl_wei = agent_info[2]
        alive = agent_info[10]
        treasury_wei = agent_info[3]
        total_fees_wei = agent_info[4]
        dep_count = agent_info[5]
        msg_count = agent_info[6]
        mode_val = agent_info[7]
        fee_bps = agent_info[8]
        liquidity = agent_info[9]
        name = agent_info[0]

        tvl_eth = float(w3.from_wei(tvl_wei, 'ether'))
        treasury_eth = float(w3.from_wei(treasury_wei, 'ether'))
        total_fees_eth = float(w3.from_wei(total_fees_wei, 'ether'))

        # Get APY
        apy_bps = 0
        try:
            apy_bps = hook.functions.estimatedAPY().call()
        except:
            pass

        modes = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
        mode_name = modes.get(mode_val, f"Unknown({mode_val})")
        alive_str = "🟢 ALIVE" if alive else "🔴 DEAD"

        print(f"\n{'─' * 50}")
        print(f"Agent #{a['index']}: {name}")
        print(f"  Hook:     {hook_addr}")
        print(f"  Owner:    {a['owner']}")
        print(f"  Status:   {alive_str}")
        print(f"  Mode:     {mode_name}")
        print(f"  Fee:      {fee_bps/100:.2f}%")
        print(f"  TVL:      {tvl_eth:.6f} ETH")
        print(f"  Treasury: {treasury_eth:.6f} ETH")
        print(f"  Fees col: {total_fees_eth:.6f} ETH")
        print(f"  Depositors: {dep_count}")
        print(f"  Messages: {msg_count}")
        print(f"  APY:      {apy_bps/100:.2f}%")
        print(f"  Liq:      {liquidity}")

        a.update({
            "tvl_eth": tvl_eth,
            "treasury_eth": treasury_eth,
            "total_fees_eth": total_fees_eth,
            "depositor_count": dep_count,
            "msg_count": msg_count,
            "mode_val": mode_val,
            "mode_name": mode_name,
            "fee_bps": fee_bps,
            "alive": alive,
            "apy_bps": apy_bps,
            "liquidity": liquidity,
        })

        if alive and tvl_eth > 0:
            active_agents.append(a)

    except Exception as e:
        print(f"\n  Agent {hook_addr[:10]}... — ERROR: {e}")

print(f"\n{'=' * 60}")
print(f"🎯 ACTIVE AGENTS (alive + TVL > 0): {len(active_agents)}")
print(f"{'=' * 60}")

# ── Process each active agent ──
results = []
for a in active_agents:
    hook_addr = a["hook"]
    print(f"\n{'#' * 55}")
    print(f"#  Processing: {a['name']}")
    print(f"#  Hook:       {hook_addr}")
    print(f"#  TVL:        {a['tvl_eth']:.6f} ETH")
    print(f"{'#' * 55}")

    hook = w3.eth.contract(address=Web3.to_checksum_address(hook_addr), abi=HOOK_ABI)
    agent_result = {
        "name": a["name"],
        "hook": hook_addr,
        "owner": a["owner"],
        "tvl_eth": a["tvl_eth"],
        "alive": a["alive"],
        "actions": [],
        "errors": [],
    }

    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price
    print(f"  Nonce: {nonce} | Gas price: {gas_price} wei")

    # 1. Simulate swap fee (0.1% of TVL)
    sim_amount = int(a["tvl_eth"] * 0.001 * 1e18)
    if sim_amount < 1000:
        sim_amount = 1000  # minimum 1000 wei

    try:
        sim_eth = float(w3.from_wei(sim_amount, 'ether'))
        print(f"  💸 simulateSwapFee({sim_eth:.6f} ETH)...", end=" ")
        tx = hook.functions.simulateSwapFee(sim_amount).build_transaction({
            'from': wallet,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': gas_price,
            'chainId': CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
        agent_result["actions"].append(f"simulateSwapFee({sim_eth:.6f} ETH) → {tx_hash.hex()}")
        nonce += 1
    except Exception as e:
        err = str(e)
        print(f"❌ {err[:100]}")
        agent_result["errors"].append(f"simulateSwapFee failed: {err}")

    # 2. If treasury > 0.001 ETH, reinvest
    if a["treasury_eth"] > 0.001:
        try:
            last_reinvest = hook.functions.lastReinvestTime().call()
            cooldown = hook.functions.REINVEST_COOLDOWN().call()
            now_ts = __import__('time').time()
            if now_ts >= last_reinvest + cooldown:
                print(f"  💸 reinvest() (treasury: {a['treasury_eth']:.6f} ETH)...", end=" ")
                tx = hook.functions.reinvest().build_transaction({
                    'from': wallet,
                    'nonce': nonce,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'chainId': CHAIN_ID,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
                agent_result["actions"].append(f"reinvest() → {tx_hash.hex()}")
                nonce += 1
            else:
                remaining = (last_reinvest + cooldown) - int(now_ts)
                print(f"  ⏳ Reinvest cooldown: {remaining}s remaining — skipped")
        except Exception as e:
            err = str(e)
            print(f"  ❌ reinvest failed: {err[:100]}")
            agent_result["errors"].append(f"reinvest failed: {err}")

    # 3. Post status message if owned by operator
    if a["owner"].lower() == Web3.to_checksum_address(OPERATOR).lower():
        ts = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M UTC')
        apy_pct = a["apy_bps"] / 100
        mode_name = a["mode_name"]
        msg = f"🤖 AgentYield | {ts} | TVL: {a['tvl_eth']:.4f} ETH | APY: {apy_pct:.2f}% | Mode: {mode_name} | Treasury: {a['treasury_eth']:.6f} ETH | Depositors: {a['depositor_count']}"
        try:
            print(f"  📝 postMessage()...", end=" ")
            tx = hook.functions.postMessage(msg).build_transaction({
                'from': wallet,
                'nonce': nonce,
                'gas': 200000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            print(f"✅ TX: {tx_hash.hex()}")
            agent_result["actions"].append(f"postMessage(status) → {tx_hash.hex()}")
            nonce += 1
        except Exception as e:
            err = str(e)
            print(f"  ❌ postMessage failed: {err[:100]}")
            agent_result["errors"].append(f"postMessage failed: {err}")

    results.append(agent_result)

# ── Summary ──
print(f"\n{'=' * 60}")
print("📊 FINAL SUMMARY")
print(f"{'=' * 60}")
print(f"Factory:      {FACTORY_ADDRESS}")
print(f"Total agents: {count}")
print(f"Active (TVL>0): {len(active_agents)}")
print(f"Operator:     {wallet}")
print()

for r in results:
    status = "✅" if not r["errors"] else "⚠️"
    print(f"{status} {r['name']:25s} | TVL: {r['tvl_eth']:.4f} ETH | Hook: {r['hook'][:10]}...")
    for a in r["actions"]:
        print(f"   └─ ✅ {a}")
    for e in r["errors"]:
        print(f"   └─ ❌ {e}")
    print()

# Also run the specific agent bot for the known deposit agent
print(f"\n{'=' * 60}")
print("🤖 RUNNING SPECIFIC AGENT BOT FOR 0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b")
print(f"{'=' * 60}")
print()
sys.stdout.flush()

# Now run the existing bot script for the specific agent too
import subprocess
result = subprocess.run(
    [sys.executable, "scripts/agent-bot.py", "--agent", "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"],
    capture_output=True, text=True, timeout=120
)
bot_output = result.stdout + "\n" + result.stderr
print(bot_output)

print(f"\n{'=' * 60}")
print("🏁 FACTORY BOT COMPLETE")
print(f"{'=' * 60}")
