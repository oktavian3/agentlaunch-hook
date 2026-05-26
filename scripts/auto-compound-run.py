#!/usr/bin/env python3
"""Run autoCompound on all agents that just received simulateSwapFee."""
import os, sys, json, time
from dotenv import load_dotenv
load_dotenv('/root/agentlaunch-hook/.env')
from web3 import Web3

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CHAIN_ID = 196

HOOK_ABI = json.loads(json.dumps([
    {"inputs":[],"name":"agentName","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"treasuryBalance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"autoCompound","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"reinvest","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"lastReinvestTime","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"REINVEST_COOLDOWN","outputs":[{"name":"","type":"uint32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"name","type":"string"},{"name":"wallet","type":"address"},{"name":"tvl","type":"uint256"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"depositorCount","type":"uint256"},{"name":"msgCount","type":"uint256"},{"name":"mode","type":"uint8"},{"name":"fee","type":"uint24"},{"name":"liquidity","type":"uint128"},{"name":"alive","type":"bool"}],"stateMutability":"view","type":"function"},
]))

w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    print("ERROR: Cannot connect to X Layer")
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
wallet = account.address
nonce = w3.eth.get_transaction_count(wallet)
gas_price = w3.eth.gas_price

agents_to_process = [
    ("AutoYieldAgent", "0x112D30a57024987973aeC338EE85030D06595F6f"),
    ("TestAgent02", "0x5aFa80D2f9aed30A0240d7Aa3A69D21C7328D55b"),
]

print("=" * 70)
print("⚡ RUNNING autoCompound ON ALL AGENTS AFTER SIMULATED FEES")
print("=" * 70)

for name, addr in agents_to_process:
    print(f"\n🔷 {name} ({addr[:10]}..)")
    try:
        hook = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=HOOK_ABI)
        info = hook.functions.getAgentInfo().call()
        treasury = info[3]
        tvl = info[2]
        alive = info[10]
        
        print(f"   Alive: {alive} | TVL: {w3.from_wei(tvl, 'ether'):.4f} ETH | Treasury: {w3.from_wei(treasury, 'ether'):.6f} ETH")
        
        if not alive or tvl == 0:
            print(f"   ⏭️  Skipping — agent not alive or no TVL")
            continue
        
        treasury_wei = info[3]
        if treasury_wei < w3.to_wei(0.0005, 'ether'):
            print(f"   ⏭️  Treasury too small ({w3.from_wei(treasury_wei, 'ether'):.6f} ETH) — skipping compound")
            continue
        
        # Try autoCompound first, fall back to reinvest
        for fn_name in ["autoCompound", "reinvest"]:
            try:
                fn = getattr(hook.functions, fn_name)
                tx = fn().build_transaction({
                    'from': wallet,
                    'nonce': nonce,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'chainId': CHAIN_ID,
                })
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                print(f"   ✅ {fn_name} succeeded! TX: {tx_hash.hex()} (status={receipt['status']})")
                nonce += 1
                time.sleep(0.5)
                break  # only one needed
            except Exception as e:
                err = str(e)
                if "cooldown" in err.lower():
                    print(f"   ⏳ {fn_name}: cooldown active — {err[:100]}")
                elif "execution reverted" in err:
                    print(f"   ⏭️  {fn_name} reverted — {err[:100]}")
                else:
                    print(f"   ❌ {fn_name} failed: {err[:120]}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

print()
print("✅ autoCompound phase complete")
