#!/usr/bin/env python3
"""
AgentYield Factory Scanner — scan ALL agents, simulate fees, post status.
Run by cron to handle the full factory.
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
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "0x74A25c7831EB3EC76402392fD394eEd31F218BCB")
OPERATOR_WALLET = "0x9D15099886F62E273eF88E17c2E53AE7f9144403"

HOOK_ABI = json.dumps([
    {"inputs":[],"name":"agentName","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"agentWallet","outputs":[{"name":"","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"treasuryBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalDeposits","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalFeesCollected","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"amount","type":"uint256"}],"name":"simulateSwapFee","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMessageCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"index","type":"uint256"}],"name":"getMessage","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"estimatedAPY","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
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

    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        print("ERROR: PRIVATE_KEY not set")
        sys.exit(1)

    account = w3.eth.account.from_key(pk)
    wallet = account.address
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    factory = w3.eth.contract(
        address=Web3.to_checksum_address(FACTORY_ADDRESS),
        abi=json.loads(FACTORY_ABI)
    )

    print(f"{'='*65}")
    print(f"🤖 AGENTYIELD FACTORY SCANNER — {ts}")
    print(f"{'='*65}")
    print(f"Operator Wallet: {OPERATOR_WALLET}")
    print(f"Signing Wallet:  {wallet}")
    print()

    # ── Step 1: Read all agents from factory ────────
    agent_count = factory.functions.getAgentCount().call()
    print(f"📊 Total agents in factory: {agent_count}")
    print()

    agents = []
    for i in range(agent_count):
        try:
            agent_data = factory.functions.agents(i).call()
            agents.append({
                "index": i,
                "hook": agent_data[0],
                "owner": agent_data[1],
                "name": agent_data[2],
                "mode": agent_data[3],
                "created_at": agent_data[4],
            })
        except Exception as e:
            print(f"  ❌ Failed to read agent {i}: {e}")

    # ── Step 2: Query each agent's info ─────────────
    results = []
    for ag in agents:
        hook_addr = Web3.to_checksum_address(ag["hook"])
        hook = w3.eth.contract(address=hook_addr, abi=json.loads(HOOK_ABI))
        print(f"\n{'─'*65}")
        print(f"Agent #{ag['index']} | {ag['name']}")
        print(f"  Hook:  {hook_addr}")
        print(f"  Owner: {ag['owner']}")
        print(f"  Mode:  {ag['mode']}")
        is_operator = ag["owner"].lower() == OPERATOR_WALLET.lower()
        is_signing = ag["owner"].lower() == wallet.lower()
        print(f"  Owned by operator: {'✅ YES' if is_operator else '❌ no'}")
        print(f"  Owned by signer:   {'✅ YES' if is_signing else '❌ no'}")

        try:
            info = hook.functions.getAgentInfo().call()
            state = {
                "name": info[0],
                "wallet": info[1],
                "tvl_wei": info[2],
                "treasury_wei": info[3],
                "total_fees_wei": info[4],
                "depositor_count": info[5],
                "msg_count": info[6],
                "mode": info[7],
                "fee_bps": info[8],
                "liquidity": info[9],
                "alive": info[10],
            }
            state["tvl_eth"] = float(w3.from_wei(state["tvl_wei"], 'ether'))
            state["treasury_eth"] = float(w3.from_wei(state["treasury_wei"], 'ether'))
            state["total_fees_eth"] = float(w3.from_wei(state["total_fees_wei"], 'ether'))
            state["fee_pct"] = state["fee_bps"] / 100.0

            print(f"  Alive:     {'✅ YES' if state['alive'] else '❌ DEAD'}")
            print(f"  TVL:       {state['tvl_eth']:.6f} ETH")
            print(f"  Treasury:  {state['treasury_eth']:.6f} ETH")
            print(f"  Fees:      {state['total_fees_eth']:.6f} ETH")
            print(f"  Depositors: {state['depositor_count']}")
            print(f"  Fee:       {state['fee_pct']:.2f}%")
            print(f"  Messages:  {state['msg_count']}")
            state["index"] = ag["index"]
            state["hook"] = hook_addr
            state["owner"] = ag["owner"]
            state["is_operator"] = is_operator
            state["hook_contract"] = hook
            results.append(state)

        except Exception as e:
            print(f"  ❌ getAgentInfo failed: {e}")
            continue

    # ── Step 3: For alive agents with TVL > 0, simulate swap fee ──
    print(f"\n{'='*65}")
    print(f"⚡ SIMULATE SWAP FEES")
    print(f"{'='*65}")

    total_simulated = 0
    for r in results:
        if r["alive"] and r["tvl_eth"] > 0:
            sim_amount = int(r["tvl_eth"] * 0.001 * 1e18)  # 0.1% of TVL
            if sim_amount > 0:
                print(f"\n  Agent: {r['name']} (index {r['index']})")
                print(f"    TVL: {r['tvl_eth']:.4f} ETH")
                print(f"    Simulating: {w3.from_wei(sim_amount, 'ether'):.6f} ETH swap fee")
                try:
                    nonce = w3.eth.get_transaction_count(wallet)
                    gas_price = w3.eth.gas_price
                    tx = r["hook_contract"].functions.simulateSwapFee(sim_amount).build_transaction({
                        'from': wallet,
                        'nonce': nonce,
                        'gas': 150000,
                        'gasPrice': gas_price,
                        'chainId': CHAIN_ID,
                    })
                    signed = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    r["simulated"] = tx_hash.hex()
                    r["simulated_amount"] = w3.from_wei(sim_amount, 'ether')
                    total_simulated += 1
                    print(f"    ✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
                except Exception as e:
                    r["simulated_error"] = str(e)
                    print(f"    ❌ Failed: {e}")
        else:
            reason = "DEAD" if not r.get("alive") else "TVL=0"
            print(f"\n  Agent: {r['name']} (index {r['index']}) — skipping ({reason})")

    # ── Step 4: Post status for operator-owned agents ──
    print(f"\n{'='*65}")
    print(f"📝 POST STATUS MESSAGES (operator-owned agents)")
    print(f"{'='*65}")

    MODES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
    MODE_EMOJI = {0: "🚀", 1: "⚖️", 2: "🛡️"}

    posted_count = 0
    for r in results:
        if r["is_operator"]:
            mode_name = MODES.get(r["mode"], "Balanced")
            emoji = MODE_EMOJI.get(r["mode"], "")
            msg = f"{emoji} AgentYield | {ts} | Agent: {r['name']} | TVL: {r['tvl_eth']:.4f} ETH | Mode: {mode_name} | Treasury: {r['treasury_eth']:.6f} ETH | Depositors: {r['depositor_count']}"
            print(f"\n  Agent: {r['name']} (index {r['index']})")
            print(f"    Message: {msg}")
            try:
                nonce = w3.eth.get_transaction_count(wallet)
                gas_price = w3.eth.gas_price
                tx = r["hook_contract"].functions.postMessage(msg).build_transaction({
                    'from': wallet,
                    'nonce': nonce,
                    'gas': 200000,
                    'gasPrice': gas_price,
                    'chainId': CHAIN_ID,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                r["status_posted"] = tx_hash.hex()
                posted_count += 1
                print(f"    ✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
            except Exception as e:
                r["status_error"] = str(e)
                print(f"    ❌ Failed: {e}")

    # ── Summary ──────────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"📋 FINAL SUMMARY — {ts}")
    print(f"{'='*65}")

    print(f"\n🏭 Factory: {FACTORY_ADDRESS}")
    print(f"📊 Total agents registered: {agent_count}")
    print(f"✅ Agents queried: {len(results)}")
    alive_count = sum(1 for r in results if r["alive"])
    alive_with_tvl = sum(1 for r in results if r["alive"] and r["tvl_eth"] > 0)
    operator_count = sum(1 for r in results if r["is_operator"])
    print(f"   Alive: {alive_count}")
    print(f"   Alive with TVL > 0: {alive_with_tvl}")
    print(f"   Operator-owned: {operator_count}")

    total_tvl = sum(r["tvl_eth"] for r in results)
    total_treasury = sum(r["treasury_eth"] for r in results)
    total_fees = sum(r["total_fees_eth"] for r in results)
    print(f"\n💰 Aggregate Stats:")
    print(f"   Total TVL:     {total_tvl:.6f} ETH")
    print(f"   Total Treasury: {total_treasury:.6f} ETH")
    print(f"   Total Fees:    {total_fees:.6f} ETH")
    print(f"   Total Depositors: {sum(r['depositor_count'] for r in results)}")

    print(f"\n⚡ Simulations:")
    simulated_ok = [r for r in results if r.get("simulated")]
    simulated_fail = [r for r in results if r.get("simulated_error")]
    print(f"   Successful: {len(simulated_ok)}")
    print(f"   Failed:     {len(simulated_fail)}")
    for r in simulated_ok:
        print(f"     ✅ {r['name']} (index {r['index']}): {r['simulated_amount']:.6f} ETH — TX: {r['simulated']}")
    for r in simulated_fail:
        print(f"     ❌ {r['name']} (index {r['index']}): {r['simulated_error']}")

    print(f"\n📝 Status Messages:")
    status_ok = [r for r in results if r.get("status_posted")]
    status_fail = [r for r in results if r.get("status_error")]
    print(f"   Posted: {len(status_ok)}")
    print(f"   Failed: {len(status_fail)}")
    for r in status_ok:
        print(f"     ✅ {r['name']} (index {r['index']}): {r['status_posted']}")
    for r in status_fail:
        print(f"     ❌ {r['name']} (index {r['index']}): {r['status_error']}")

    print(f"\n{'─'*65}")
    print(f"🏁 Scan complete — {agent_count} agents checked, {total_simulated} fees simulated, {posted_count} statuses posted")
    print(f"{'─'*65}")


if __name__ == "__main__":
    main()
