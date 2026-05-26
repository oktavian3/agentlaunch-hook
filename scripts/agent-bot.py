#!/usr/bin/env python3
"""
AgentYield Bot — AI Agent Engine
=================================
The brains behind each AgentYield Hook. Runs as a cron job or daemon.

What it does every cycle:
1. Reads on-chain state (treasury, TVL, depositors, current tick)
2. Decides what to do (reinvest? rebalance? adjust fee?)
3. Executes actions via agent wallet
4. Posts on-chain status messages

Usage:
  python3 scripts/agent-bot.py                    # run once
  python3 scripts/agent-bot.py --loop --interval 300  # every 5 min
  python3 scripts/agent-bot.py --agent 0x...      # specific agent

Cron (every 30 min):
  */30 * * * * cd /path/to/agentyield-hook && python3 scripts/agent-bot.py
"""

import os
import sys
import json
import time
import argparse
import random
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
CHAIN_ID = 196
FACTORY_ADDRESS = os.getenv("FACTORY_ADDRESS", "")

# If no AGENT_HOOK set, bot scans factory for all agents
AGENT_HOOK = os.getenv("AGENT_HOOK", "")

# ═══════════════════════════════════════════════════════════
# ABIs
# ═══════════════════════════════════════════════════════════

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


class AgentYieldBot:
    """AI bot managing AgentYield Hooks on X Layer."""

    MODES = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}
    MODE_EMOJI = {0: "🚀", 1: "⚖️", 2: "🛡️"}

    def __init__(self, hook_address=None):
        from web3 import Web3
        self.Web3 = Web3
        self.w3 = Web3(Web3.HTTPProvider(RPC))

        if not self.w3.is_connected():
            print(f"ERROR: Cannot connect to {RPC}")
            sys.exit(1)

        # Agent wallet
        self.pk = os.environ.get("PRIVATE_KEY")
        if not self.pk:
            print("ERROR: PRIVATE_KEY not set")
            sys.exit(1)

        self.account = self.w3.eth.account.from_key(self.pk)
        self.wallet = self.account.address

        self.hook = None
        if hook_address:
            self.hook = self.w3.eth.contract(
                address=self.Web3.to_checksum_address(hook_address),
                abi=json.loads(HOOK_ABI)
            )

        self.ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        self.actions = []

    def log(self, msg):
        print(f"  {msg}")

    def action(self, msg):
        print(f"  ✅ {msg}")
        self.actions.append(msg)

    # ── Phase 1: Read ─────────────────────────────────────

    def read_agent_state(self):
        """Read full state from the agent Hook."""
        if not self.hook:
            return {}

        try:
            info = self.hook.functions.getAgentInfo().call()
            state = {
                "name": info[0],
                "wallet": info[1],
                "tvl_eth": float(self.w3.from_wei(info[2], 'ether')),
                "treasury_eth": float(self.w3.from_wei(info[3], 'ether')),
                "total_fees_eth": float(self.w3.from_wei(info[4], 'ether')),
                "depositor_count": info[5],
                "msg_count": info[6],
                "mode": info[7],
                "fee_bps": info[8],
                "liquidity": info[9],
                "alive": info[10],
                "apy_bps": self.hook.functions.estimatedAPY().call(),
            }
            state["fee_pct"] = state["fee_bps"] / 100
            state["apy_pct"] = state["apy_bps"] / 100

            self.log(f"Agent: {state['name']}")
            self.log(f"Mode: {self.MODES.get(state['mode'], '?')} | Fee: {state['fee_pct']:.2f}%")
            self.log(f"TVL: {state['tvl_eth']:.4f} ETH | Treasury: {state['treasury_eth']:.6f} ETH")
            self.log(f"Depositors: {state['depositor_count']} | APY: {state['apy_pct']:.2f}%")

            return state
        except Exception as e:
            self.log(f"Read error: {e}")
            return {}

    # ── Phase 2: Decide ───────────────────────────────────

    def decide(self, state):
        """AI decision engine."""
        print(f"\n🧠 [DECIDE]")

        decisions = []

        # Decision 1: Simulate swap fee (generate yield for APY)
        if state.get("tvl_eth", 0) > 0:
            # Simulate daily yield ~0.1% of TVL per cycle
            sim_amount = int(state["tvl_eth"] * 0.001 * 1e18)
            if sim_amount > 0:
                decisions.append(("simulate_fee", sim_amount))
                self.log(f"💸 Simulate swap fee: {self.w3.from_wei(sim_amount, 'ether'):.6f} ETH")

        # Decision 2: Reinvest?
        if state.get("treasury_eth", 0) > 0.001:  # Min 0.001 ETH
            can_reinvest = True
            try:
                last = self.hook.functions.lastReinvestTime().call()
                cooldown = self.hook.functions.REINVEST_COOLDOWN().call()
                if time.time() < last + cooldown:
                    can_reinvest = False
                    remaining = (last + cooldown) - int(time.time())
                    self.log(f"⏳ Reinvest cooldown: {remaining}s remaining")
            except:
                pass

            if can_reinvest:
                decisions.append("reinvest")
                self.log(f"💸 Reinvest {state['treasury_eth']:.6f} ETH → LP")

        # Decision 2: Post status message?
        if random.random() < 0.3:  # ~30% of cycles
            decisions.append("post_status")
            self.log(f"📝 Post on-chain status")

        if not decisions:
            self.log("✅ All nominal — no action needed")

        return decisions

    # ── Phase 3: Execute ──────────────────────────────────

    def execute(self, decisions, state):
        """Execute agent actions."""
        print(f"\n⚡ [EXECUTE]")

        nonce = self.w3.eth.get_transaction_count(self.wallet)
        gas_price = self.w3.eth.gas_price

        for decision in decisions:
            if isinstance(decision, tuple):
                cmd, amount = decision
                if cmd == "simulate_fee":
                    self._do_simulate_fee(amount, nonce, gas_price)
                    nonce += 1
            elif decision == "reinvest":
                self._do_reinvest(nonce, gas_price)
                nonce += 1

            elif decision == "post_status":
                self._do_post_status(state, nonce, gas_price)
                nonce += 1

    def _do_simulate_fee(self, amount, nonce, gas_price):
        if not self.hook:
            return
        try:
            tx = self.hook.functions.simulateSwapFee(amount).build_transaction({
                'from': self.wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            self.action(f"Simulated fee ✅ {self.w3.from_wei(amount, 'ether'):.6f} ETH → treasury")
        except Exception as e:
            self.log(f"❌ Simulate fee failed: {e}")

    def _do_reinvest(self, nonce, gas_price):
        if not self.hook:
            return
        try:
            tx = self.hook.functions.reinvest().build_transaction({
                'from': self.wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            self.action(f"Reinvested ✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
        except Exception as e:
            self.log(f"❌ Reinvest failed: {e}")

    def _do_post_status(self, state, nonce, gas_price):
        if not self.hook:
            return

        mode_name = self.MODES.get(state.get("mode", 1), "Balanced")
        emoji = self.MODE_EMOJI.get(state.get("mode", 1), "")
        tvl = state.get('tvl_eth', 0)
        apy = state.get('apy_pct', 0)
        treasury = state.get('treasury_eth', 0)

        msg = f"{emoji} AgentYield | {self.ts} | TVL: {tvl:.4f} ETH | APY: {apy:.2f}% | Mode: {mode_name} | Treasury: {treasury:.6f} ETH | Depositors: {state.get('depositor_count', 0)}"

        try:
            tx = self.hook.functions.postMessage(msg).build_transaction({
                'from': self.wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': gas_price,
                'chainId': CHAIN_ID,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            self.action(f"Status posted ✅ TX: {tx_hash.hex()}")
        except Exception as e:
            self.log(f"❌ Post failed: {e}")

    # ── Run ────────────────────────────────────────────────

    def run(self):
        """Full AgentYield bot cycle."""
        print(f"\n{'=' * 55}")
        print(f"🤖 AGENTYIELD BOT — {self.ts}")
        print(f"{'=' * 55}")
        print(f"Wallet: {self.wallet}")
        print(f"Hook:   {getattr(self.hook, 'address', 'N/A') if self.hook else 'N/A'}")

        state = self.read_agent_state()
        if not state:
            self.log("⚠️ No state to process")
            return {"status": "skipped"}

        decisions = self.decide(state)
        self.execute(decisions, state)

        print(f"\n{'─' * 55}")
        print(f"📋 Summary: {len(self.actions)} action(s)")
        for a in self.actions:
            print(f"  ✅ {a}")
        print(f"{'─' * 55}\n")

        return {"state": state, "actions": self.actions}


def main():
    parser = argparse.ArgumentParser(description="AgentYield AI Bot")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds")
    parser.add_argument("--agent", type=str, default=AGENT_HOOK, help="Hook address")
    args = parser.parse_args()

    bot = AgentYieldBot(hook_address=args.agent)

    if args.loop:
        print(f"🔄 Loop mode — every {args.interval}s")
        while True:
            try:
                bot.run()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n👋 Shutdown")
                break
            except Exception as e:
                print(f"❌ {e}")
                time.sleep(args.interval)
    else:
        bot.run()


if __name__ == "__main__":
    main()
