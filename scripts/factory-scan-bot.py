#!/usr/bin/env python3
"""
Factory Scan Bot — Run AgentYield bot for ALL agents in factory.
Calls simulateSwapFee for every alive agent with TVL > 0.
Posts status for agents owned by the operator wallet.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "")
PK = os.getenv("PRIVATE_KEY", "")
CHAIN_ID = 196

OPERATOR_WALLET = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

MODE_NAMES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
MODE_EMOJI = {0: "🚀", 1: "⚖️", 2: "🛡️"}

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
    {"inputs":[{"name":"percentage","type":"uint256"}],"name":"autoTrade","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMessageCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"index","type":"uint256"}],"name":"getMessage","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getDepositorCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
])

FACTORY_ABI = json.dumps([
    {"inputs":[],"name":"getAgentCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"","type":"uint256"}],"name":"agents","outputs":[{"name":"hookAddress","type":"address"},{"name":"owner","type":"address"},{"name":"name","type":"string"},{"name":"mode","type":"uint8"},{"name":"createdAt","type":"uint256"}],"stateMutability":"view","type":"function"},
])


def main():
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(RPC))

    if not w3.is_connected():
        print("ERROR: Cannot connect to X Layer RPC")
        sys.exit(1)

    if not PK:
        print("ERROR: PRIVATE_KEY not set")
        sys.exit(1)

    account = w3.eth.account.from_key(PK)
    wallet = account.address
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    print(f"{'='*65}")
    print(f"🏭 FACTORY SCAN BOT — {ts}")
    print(f"{'='*65}")
    print(f"Operator:  {wallet}")
    print(f"Factory:   {FACTORY_ADDRESS}")
    print(f"RPC:       {RPC}")
    print()

    factory = w3.eth.contract(
        address=Web3.to_checksum_address(FACTORY_ADDRESS),
        abi=json.loads(FACTORY_ABI)
    )

    # ── Step 1: List all agents ────────────────────────────
    agent_count = factory.functions.getAgentCount().call()
    print(f"📋 Total agents registered: {agent_count}")
    print()

    if agent_count == 0:
        print("No agents found. Nothing to do.")
        return

    all_agents = []
    for i in range(agent_count):
        try:
            result = factory.functions.agents(i).call()
            all_agents.append({
                "index": i,
                "hook": result[0],
                "owner": result[1],
                "name": result[2],
                "mode": result[3],
                "created_at": result[4],
            })
        except Exception as e:
            print(f"  ⚠️  Agent #{i}: Read error: {e}")

    print(f"{'─'*65}")
    print(f"🔍 Scanning {len(all_agents)} agent(s)...")
    print()

    # ── Step 2: Check each agent ───────────────────────────
    agents_with_tvl = []
    summary_lines = []

    for a in all_agents:
        hook_addr = a["hook"]
        owner_addr = a["owner"]
        agent_name = a["name"]
        agent_idx = a["index"]

        try:
            hook = w3.eth.contract(
                address=Web3.to_checksum_address(hook_addr),
                abi=json.loads(HOOK_ABI)
            )
            info = hook.functions.getAgentInfo().call()

            tvl_wei = info[2]
            tvl_eth = float(w3.from_wei(tvl_wei, 'ether'))
            treasury_eth = float(w3.from_wei(info[3], 'ether'))
            total_fees_eth = float(w3.from_wei(info[4], 'ether'))
            depositor_count = info[5]
            msg_count = info[6]
            mode = info[7]
            fee_bps = info[8]
            alive = info[10]

            try:
                apy_bps = hook.functions.estimatedAPY().call()
                apy_pct = apy_bps / 100
            except:
                apy_pct = 0.0

            mode_name = MODE_NAMES.get(mode, "?")
            mode_emoji = MODE_EMOJI.get(mode, "❓")
            is_operator = owner_addr.lower() == OPERATOR_WALLET.lower()

            status_icon = "✅" if alive else "💀"

            print(f"  #{agent_idx} {status_icon} {agent_name}")
            print(f"      Hook:  {hook_addr}")
            print(f"      Owner: {owner_addr} {'[OPERATOR]' if is_operator else ''}")
            print(f"      Mode:  {mode_emoji} {mode_name} | Fee: {fee_bps/100:.2f}%")
            print(f"      TVL:   {tvl_eth:.4f} ETH | Treasury: {treasury_eth:.6f} ETH")
            print(f"      Depositors: {depositor_count} | Msgs: {msg_count} | APY: {apy_pct:.2f}%")
            print(f"      Alive: {alive}")

            if tvl_eth > 0 and alive:
                agents_with_tvl.append({
                    "hook": hook,
                    "hook_addr": hook_addr,
                    "name": agent_name,
                    "tvl_eth": tvl_eth,
                    "treasury_eth": treasury_eth,
                    "depositor_count": depositor_count,
                    "mode": mode,
                    "mode_name": mode_name,
                    "is_operator": is_operator,
                    "apy_pct": apy_pct,
                    "info": info,
                })
                print(f"      ⏩ Will simulate swap fee (TVL > 0)")
            elif tvl_eth > 0 and not alive:
                print(f"      ⏭️  TVL > 0 but agent is dead — skipping fee sim")
            else:
                print(f"      ⏭️  TVL = 0 — skipping")

            summary_lines.append({
                "idx": agent_idx,
                "name": agent_name,
                "hook": hook_addr,
                "tvl": tvl_eth,
                "alive": alive,
                "treasury": treasury_eth,
                "depositors": depositor_count,
                "mode": mode_name,
                "is_operator": is_operator,
            })

            print()

        except Exception as e:
            print(f"  ⚠️  #{agent_idx} {hook_addr}: Error reading info: {e}")
            print()

    print(f"{'─'*65}")
    print(f"⚡ Agents with TVL > 0 & alive: {len(agents_with_tvl)}")
    print()

    # ── Step 3: Execute for each ───────────────────────────
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    actions_taken = []

    for a in agents_with_tvl:
        hook = a["hook"]
        name = a["name"]
        tvl_eth = a["tvl_eth"]
        treasury_eth = a["treasury_eth"]
        is_operator = a["is_operator"]
        info = a["info"]

        print(f"\n  ═══ Processing: {name} ═══")
        print(f"  Address: {a['hook_addr']}")

        # Phase A: Simulate swap fee (daily yield ~0.1% TVL)
        sim_amount = int(tvl_eth * 0.001 * 1e18)
        if sim_amount > 0:
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
                w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"    ✅ simulateSwapFee({w3.from_wei(sim_amount, 'ether'):.6f} ETH) → TX: {tx_hash.hex()}")
                actions_taken.append(f"Simulated fee {w3.from_wei(sim_amount, 'ether'):.6f} ETH on {name}")
                nonce += 1
            except Exception as e:
                print(f"    ❌ simulateSwapFee failed: {e}")

        # Phase B: Review treasury for reinvest
        if treasury_eth > 0.001:
            try:
                last = hook.functions.lastReinvestTime().call()
                cooldown = hook.functions.REINVEST_COOLDOWN().call()
                can_reinvest = (time.time() >= last + cooldown)
                if can_reinvest:
                    tx = hook.functions.reinvest().build_transaction({
                        'from': wallet,
                        'nonce': nonce,
                        'gas': 150000,
                        'gasPrice': gas_price,
                        'chainId': CHAIN_ID,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    print(f"    ✅ reinvest → TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
                    actions_taken.append(f"Reinvested {treasury_eth:.6f} ETH on {name}")
                    nonce += 1
                else:
                    remaining = (last + cooldown) - int(time.time())
                    print(f"    ⏳ Reinvest cooldown active: {remaining}s remaining")
            except Exception as e:
                print(f"    ❌ reinvest failed: {e}")

        # Phase C: Post status message if operator-owned
        if is_operator:
            mode_name = MODE_NAMES.get(a["mode"], "Balanced")
            emoji = MODE_EMOJI.get(a["mode"], "")
            msg = f"{emoji} AgentYield | {ts} | TVL: {tvl_eth:.4f} ETH | APY: {a['apy_pct']:.2f}% | Mode: {mode_name} | Treasury: {treasury_eth:.6f} ETH | Depositors: {info[5]}"
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
                w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"    ✅ Status posted → TX: {tx_hash.hex()}")
                actions_taken.append(f"Posted status on {name}")
                nonce += 1
            except Exception as e:
                print(f"    ❌ Status post failed: {e}")

    # ── Step 4: Also run the specific agent bot ────────────
    print(f"\n{'='*65}")
    print(f"🔵 Running primary agent bot for 0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b")
    print(f"{'='*65}")
    print()

    specific_hook_addr = "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"
    try:
        specific_hook = w3.eth.contract(
            address=Web3.to_checksum_address(specific_hook_addr),
            abi=json.loads(HOOK_ABI)
        )
        specific_info = specific_hook.functions.getAgentInfo().call()
        specific_tvl = float(w3.from_wei(specific_info[2], 'ether'))
        specific_treasury = float(w3.from_wei(specific_info[3], 'ether'))
        specific_alive = specific_info[10]
        specific_name = specific_info[0]
        specific_mode = specific_info[7]

        print(f"  Agent: {specific_name}")
        print(f"  TVL: {specific_tvl:.4f} ETH | Alive: {specific_alive}")
        print(f"  Treasury: {specific_treasury:.6f} ETH")

        if specific_tvl > 0 and specific_alive:
            sim_amount = int(specific_tvl * 0.001 * 1e18)
            if sim_amount > 0:
                try:
                    tx = specific_hook.functions.simulateSwapFee(sim_amount).build_transaction({
                        'from': wallet,
                        'nonce': nonce,
                        'gas': 150000,
                        'gasPrice': gas_price,
                        'chainId': CHAIN_ID,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    w3.eth.wait_for_transaction_receipt(tx_hash)
                    print(f"    ✅ simulateSwapFee({w3.from_wei(sim_amount, 'ether'):.6f} ETH)")
                    actions_taken.append(f"Simulated fee {w3.from_wei(sim_amount, 'ether'):.6f} ETH on {specific_name} (primary)")
                    nonce += 1
                except Exception as e:
                    print(f"    ❌ simulateSwapFee failed on primary: {e}")

            # Post status on primary agent too
            mode_name = MODE_NAMES.get(specific_mode, "Balanced")
            emoji = MODE_EMOJI.get(specific_mode, "")
            try:
                apy = specific_hook.functions.estimatedAPY().call() / 100
            except:
                apy = 0.0
            msg = f"{emoji} AgentYield | {ts} | TVL: {specific_tvl:.4f} ETH | APY: {apy:.2f}% | Mode: {mode_name} | Treasury: {specific_treasury:.6f} ETH"
            try:
                tx = specific_hook.functions.postMessage(msg).build_transaction({
                    'from': wallet,
                    'nonce': nonce,
                    'gas': 150000,
                    'gasPrice': gas_price,
                    'chainId': CHAIN_ID,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"    ✅ Status posted on primary agent")
                actions_taken.append(f"Posted status on {specific_name} (primary)")
                nonce += 1
            except Exception as e:
                print(f"    ❌ Status post failed on primary: {e}")
        else:
            print(f"  ⏭️  TVL = 0 or dead — no action needed")

    except Exception as e:
        print(f"  ❌ Error with primary agent: {e}")

    # ── Final Summary ──────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"📊 FINAL SUMMARY — {ts}")
    print(f"{'='*65}")
    print(f"\nTotal agents in factory: {agent_count}")
    print(f"Alive agents with TVL > 0: {len(agents_with_tvl)}")
    print(f"Actions taken: {len(actions_taken)}")
    for a in actions_taken:
        print(f"  ✅ {a}")
    print()

    print(f"\n{'─'*65}")
    print(f"Agent Inventory:")
    print(f"{'─'*65}")
    for s in summary_lines:
        alive_str = "✅ Alive" if s["alive"] else "💀 Dead"
        op_str = " [OPERATOR]" if s["is_operator"] else ""
        print(f"  #{s['idx']} {s['name']:20s} | TVL: {s['tvl']:>8.4f} ETH | {alive_str}{op_str}")
    print()
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
