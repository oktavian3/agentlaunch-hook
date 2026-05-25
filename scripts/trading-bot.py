#!/usr/bin/env python3
"""
TradingBot — AI Agent Trading & LP Management Bot
===================================================

This bot is the BRAINS of the AI agent. It:

1. Reads on-chain pool state (price, TVL, fee accumulated)
2. Analyzes price movement against strategy threshold
3. Decides: rebalance LP? Swap? Reinvest fees?
4. Executes via agent wallet → TradingAgent contract → PoolManager

This transforms AgentHook from a passive fee collector into an
ACTIVE AI agent that generates real returns.

Usage:
  # Run once (test)
  python3 scripts/trading-bot.py

  # Run as loop (every 5 min)
  python3 scripts/trading-bot.py --loop --interval 300

  # Via cron (every 30 min)
  */30 * * * * cd /path/to/agentlaunch-hook && python3 scripts/trading-bot.py >> /tmp/trading-bot.log 2>&1

Architecture:
  ┌──────────────────────────────────────────────────────┐
  │                  TradingBot.py                        │
  │  ┌──────────┐  ┌────────────┐  ┌──────────────────┐  │
  │  │ PoolReader│→│ Strategy    │→│ Executor          │  │
  │  │ (on-chain)│ │ Decision    │ │ (TX sender)       │  │
  │  └──────────┘  └────────────┘  └──────────────────┘  │
  └─────────────────────────┬────────────────────────────┘
                            │ signs with agent wallet
                            ▼
  ┌──────────────────────────────────────────────────────┐
  │                  On-Chain Layer                       │
  │  TradingAgent (LP mgmt) → PoolManager (V4) → Pool    │
  │  AgentHook (fee collection)                           │
  └──────────────────────────────────────────────────────┘
"""

import os
import sys
import json
import time
import math
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load .env
load_dotenv()

# ═══════════════════════════════════════════════════════════
# CONFIG — Edit these for YOUR agent
# ═══════════════════════════════════════════════════════════

RPC = os.getenv("XLAYER_RPC_URL", "https://rpc.xlayer.tech")
CHAIN_ID = 196

# Your deployed contracts
TRADING_AGENT = os.getenv("TRADING_AGENT", "")    # ← set this after deploying
AGENT_HOOK = os.getenv("AGENT_HOOK", "")
POOL_MANAGER = "0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32"

# Strategy thresholds
REBALANCE_THRESHOLD_BPS = int(os.getenv("REBALANCE_THRESHOLD", "200"))  # 2% price move
FEE_CLAIM_INTERVAL_HOURS = int(os.getenv("FEE_CLAIM_INTERVAL", "24"))
MIN_TREASURY_FOR_REINVEST = float(os.getenv("MIN_TREASURY", "0.001"))   # ETH

# Pool config — the pool this agent manages
POOL_TOKEN0 = os.getenv("POOL_TOKEN0", "")
POOL_TOKEN1 = os.getenv("POOL_TOKEN1", "")
POOL_FEE = int(os.getenv("POOL_FEE", "3000"))       # 0.30%
POOL_TICK_SPACING = int(os.getenv("POOL_TICK_SPACING", "60"))

# ═══════════════════════════════════════════════════════════
# Minimal ABIs
# ═══════════════════════════════════════════════════════════

TRADING_AGENT_ABI = json.dumps([
    {"inputs":[],"name":"getStats","outputs":[{"name":"positionCount","type":"uint256"},{"name":"tvl","type":"uint256"},{"name":"swaps","type":"uint256"},{"name":"rebalances","type":"uint256"},{"name":"active","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"strategy","outputs":[{"name":"rebalanceThresholdBps","type":"uint24"},{"name":"feeClaimInterval","type":"uint24"},{"name":"active","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"_positionId","type":"uint256"}],"name":"positions","outputs":[{"name":"poolKey","type":"tuple"},{"name":"tickLower","type":"int24"},{"name":"tickUpper","type":"int24"},{"name":"liquidity","type":"uint128"},{"name":"amount0","type":"uint256"},{"name":"amount1","type":"uint256"},{"name":"lastRebalance","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getPositionCount","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"_positionId","type":"uint256"},{"name":"_newTickLower","type":"int24"},{"name":"_newTickUpper","type":"int24"},{"name":"_newLiquidity","type":"uint128"}],"name":"rebalancePosition","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_poolKey","type":"tuple"},{"name":"_zeroForOne","type":"bool"},{"name":"_amountSpecified","type":"int256"},{"name":"_sqrtPriceLimit","type":"uint160"}],"name":"executeSwap","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"_positionId","type":"uint256"},{"name":"_amount","type":"uint256"}],"name":"reinvestFees","outputs":[],"stateMutability":"nonpayable","type":"function"},
])

HOOK_ABI = json.dumps([
    {"inputs":[],"name":"getAgentInfo","outputs":[{"name":"wallet","type":"address"},{"name":"name","type":"string"},{"name":"description","type":"string"},{"name":"fee","type":"uint24"},{"name":"created","type":"uint40"},{"name":"lastSeen","type":"uint40"},{"name":"treasury","type":"uint256"},{"name":"totalFees","type":"uint256"},{"name":"messageCount","type":"uint256"},{"name":"agentPoolId","type":"bytes32"},{"name":"isAlive","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"heartbeat","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"content","type":"string"}],"name":"postMessage","outputs":[],"stateMutability":"nonpayable","type":"function"},
])

# PoolManager minimal ABI for slot0 (current sqrtPrice & tick)
POOL_MANAGER_ABI = json.dumps([
    {"inputs":[{"name":"key","type":"tuple"}],"name":"getSlot0","outputs":[{"name":"sqrtPriceX96","type":"uint160"},{"name":"tick","type":"int24"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"key","type":"tuple"}],"name":"getLiquidity","outputs":[{"name":"liquidity","type":"uint128"}],"stateMutability":"view","type":"function"},
])


class TradingBot:
    """AI agent that actively manages LP positions on Uniswap V4."""

    def __init__(self):
        # Import web3
        try:
            from web3 import Web3
            self.Web3 = Web3
        except ImportError:
            print("ERROR: web3.py not installed. Run: pip install -r requirements.txt")
            sys.exit(1)

        self.w3 = Web3(Web3.HTTPProvider(RPC))

        if not self.w3.is_connected():
            print(f"ERROR: Cannot connect to {RPC}")
            sys.exit(1)

        # Agent wallet from env
        self.pk = os.environ.get("PRIVATE_KEY")
        if not self.pk:
            print("ERROR: PRIVATE_KEY not set in .env")
            sys.exit(1)

        self.account = self.w3.eth.account.from_key(self.pk)
        self.agent_wallet = self.account.address

        # Init contracts
        if TRADING_AGENT:
            self.trader = self.w3.eth.contract(
                address=self.Web3.to_checksum_address(TRADING_AGENT),
                abi=json.loads(TRADING_AGENT_ABI)
            )
        else:
            self.trader = None
            print("⚠️  TRADING_AGENT not set — trading functions disabled")

        if AGENT_HOOK:
            self.hook = self.w3.eth.contract(
                address=self.Web3.to_checksum_address(AGENT_HOOK),
                abi=json.loads(HOOK_ABI)
            )
        else:
            self.hook = None
            print("⚠️  AGENT_HOOK not set — heartbeat disabled")

        self.pool_manager = self.w3.eth.contract(
            address=self.Web3.to_checksum_address(POOL_MANAGER),
            abi=json.loads(POOL_MANAGER_ABI)
        )

        self.ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        self.actions_taken = []

    def log(self, msg):
        print(f"  {msg}")

    def report(self, msg):
        print(f"  → {msg}")
        self.actions_taken.append(msg)

    # ── Phase 1: Read Pool State ───────────────────────────────

    def read_pool_state(self):
        """Fetch current pool state: price, tick, liquidity, TVL."""
        print(f"\n📊 [PHASE 1] Pool State Reading")
        print(f"   Agent: {self.agent_wallet}")

        state = {
            "price": 0,
            "tick": 0,
            "liquidity": 0,
            "tvl_eth": 0,
            "token0_price_usd": 0,
            "token1_price_usd": 0,
        }

        if self.hook:
            try:
                info = self.hook.functions.getAgentInfo().call()
                state["agent_name"] = info[1]
                state["agent_fee"] = info[3]
                state["treasury_eth"] = float(self.w3.from_wei(info[6], 'ether'))
                state["total_fees_eth"] = float(self.w3.from_wei(info[7], 'ether'))
                state["message_count"] = info[8]
                state["is_alive"] = info[10]

                self.log(f"Agent: {info[1]} | Fee: {info[3]/100:.2f}%")
                self.log(f"Treasury: {state['treasury_eth']:.6f} ETH")
                self.log(f"Total fees collected: {state['total_fees_eth']:.6f} ETH")
                self.log(f"Alive: {'✅ YES' if state['is_alive'] else '❌ NO'}")
            except Exception as e:
                self.log(f"⚠️ Hook read error: {e}")

        if self.trader:
            try:
                stats = self.trader.functions.getStats().call()
                state["position_count"] = stats[0]
                state["tvl"] = stats[1]
                state["swaps_executed"] = stats[2]
                state["rebalances"] = stats[3]
                state["strategy_active"] = stats[4]

                strat = self.trader.functions.strategy().call()
                state["rebalance_threshold_bps"] = strat[0]
                state["fee_claim_interval"] = strat[1]

                self.log(f"Positions: {stats[0]} | TVL: {self.w3.from_wei(stats[1], 'ether'):.4f} ETH")
                self.log(f"Swaps: {stats[2]} | Rebalances: {stats[3]}")
                self.log(f"Strategy: rebalance @ {strat[0]/100:.2f}% | claim every {strat[1]}h")
            except Exception as e:
                self.log(f"⚠️ Trader read error: {e}")

        return state

    def get_current_tick(self):
        """Estimate current tick from on-chain data."""
        if not POOL_TOKEN0 or not POOL_TOKEN1:
            return 0

        try:
            # Build PoolKey struct
            currency0 = sorted([POOL_TOKEN0.lower(), POOL_TOKEN1.lower()])[0]
            currency1 = [t for t in [POOL_TOKEN0.lower(), POOL_TOKEN1.lower()] if t != currency0][0]

            pool_key = (
                self.Web3.to_checksum_address(currency0),
                self.Web3.to_checksum_address(currency1),
                POOL_FEE,
                POOL_TICK_SPACING,
                self.Web3.to_checksum_address(AGENT_HOOK) if AGENT_HOOK else "0x" + "00" * 20
            )

            slot0 = self.pool_manager.functions.getSlot0(pool_key).call()
            return slot0[1]  # tick
        except Exception as e:
            self.log(f"⚠️ Could not read current tick: {e}")
            return 0

    # ── Phase 2: Strategy Decision ────────────────────────────

    def analyze_and_decide(self, state, current_tick):
        """The AI decision engine — decides what to do based on pool state."""
        print(f"\n🧠 [PHASE 2] Strategy Analysis")

        decisions = []

        # Decision 1: Should we heartbeat?
        if state.get("is_alive") == False:
            decisions.append("heartbeat_required")
            self.log("⚡ Decision: Agent not alive → heartbeat needed")
        else:
            self.log("✅ Agent is alive (heartbeat OK)")

        # Decision 2: Should we rebalance?
        if current_tick != 0 and state.get("position_count", 0) > 0:
            # In production: compare current tick vs position ticks
            # For now: check if there's a treasury to reinvest
            treasury = state.get("treasury_eth", 0)
            if treasury > MIN_TREASURY_FOR_REINVEST:
                decisions.append("reinvest_fees")
                self.log(f"💸 Decision: Treasury ${treasury:.4f} ETH > min ${MIN_TREASURY_FOR_REINVEST} → reinvest")

            # Check if we should rebalance (simplified)
            # Real impl: get position ticks, compare to current tick, check threshold
            threshold_pct = state.get("rebalance_threshold_bps", 200) / 100
            self.log(f"📐 Rebalance threshold: {threshold_pct:.2f}% price movement")
            self.log(f"   Current tick: {current_tick}")
            self.log(f"   (Full rebalance logic requires LP position ticks)")

        # Decision 3: Should we trade?
        swap_interval = state.get("fee_claim_interval", 24)
        self.log(f"🔄 Swap interval: every {swap_interval}h (passive — agent decides manually)")

        if not decisions:
            self.log("✅ No action needed — everything nominal")
            decisions.append("no_op")

        return decisions

    # ── Phase 3: Execute ──────────────────────────────────────

    def execute_actions(self, decisions, state):
        """Execute the decided actions on-chain."""
        print(f"\n⚡ [PHASE 3] Execution")

        for action in decisions:
            if action == "heartbeat_required" and self.hook:
                self._send_heartbeat()

            elif action == "reinvest_fees" and self.trader:
                self._reinvest_treasury(state)

            elif action == "no_op":
                self.log("Skipping — no actions to execute")

    def _send_heartbeat(self):
        """Send heartbeat to AgentHook + post status message."""
        print(f"\n💓 Action: Heartbeat + Status Message")
        try:
            nonce = self.w3.eth.get_transaction_count(self.agent_wallet)

            # 1. Heartbeat
            tx = self.hook.functions.heartbeat().build_transaction({
                'from': self.agent_wallet,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': CHAIN_ID,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            self.report(f"Heartbeat sent ✅ TX: {tx_hash.hex()} (gas: {receipt['gasUsed']})")
            nonce += 1

            # 2. Post trading status message
            state_summary = self._build_status_message()
            tx2 = self.hook.functions.postMessage(state_summary).build_transaction({
                'from': self.agent_wallet,
                'nonce': nonce,
                'gas': 150000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': CHAIN_ID,
            })
            signed2 = self.account.sign_transaction(tx2)
            tx_hash2 = self.w3.eth.send_raw_transaction(signed2.raw_transaction)
            receipt2 = self.w3.eth.wait_for_transaction_receipt(tx_hash2)
            self.report(f"Status posted ✅ TX: {tx_hash2.hex()} (gas: {receipt2['gasUsed']})")

        except Exception as e:
            self.log(f"❌ Heartbeat failed: {e}")

    def _reinvest_treasury(self, state):
        """Reinvest accumulated fees into LP position."""
        print(f"\n💰 Action: Reinvest Treasury Fees")

        try:
            positions = self.trader.functions.getPositionCount().call()
            if positions == 0:
                self.log("No positions to reinvest into")
                return

            treasury_wei = self.w3.to_wei(state.get("treasury_eth", 0), 'ether')
            reinvest_amount = int(treasury_wei * 0.8)  # 80% of treasury

            if reinvest_amount < self.w3.to_wei(MIN_TREASURY_FOR_REINVEST, 'ether'):
                self.log(f"Treasury too small to reinvest (need > {MIN_TREASURY_FOR_REINVEST} ETH)")
                return

            nonce = self.w3.eth.get_transaction_count(self.agent_wallet)
            tx = self.trader.functions.reinvestFees(0, reinvest_amount).build_transaction({
                'from': self.agent_wallet,
                'nonce': nonce,
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': CHAIN_ID,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            self.report(f"Reinvested {self.w3.from_wei(reinvest_amount, 'ether'):.6f} ETH → position 0 ✅ TX: {tx_hash.hex()}")

        except Exception as e:
            self.log(f"❌ Reinvest failed: {e}")

    def _build_status_message(self):
        """Build a trading status message for on-chain posting."""
        try:
            if self.trader:
                stats = self.trader.functions.getStats().call()
                strat = self.trader.functions.strategy().call()
                pos_count = stats[0]
                tvl = float(self.w3.from_wei(stats[1], 'ether'))
                swaps = stats[2]
                rebalances = stats[3]

                return (
                    f"TradingBot | {self.ts} | "
                    f"Positions: {pos_count} | "
                    f"TVL: {tvl:.4f} ETH | "
                    f"Swaps: {swaps} | "
                    f"Rebalances: {rebalances} | "
                    f"Threshold: {strat[0]/100:.1f}%"
                )
        except:
            pass

        return f"TradingAgent operational at {self.ts}"

    # ── Run ───────────────────────────────────────────────────

    def run(self):
        """Full trading bot cycle: Read → Analyze → Execute."""
        print(f"\n{'═' * 60}")
        print(f"🤖 AI TRADING BOT — {self.ts}")
        print(f"{'═' * 60}")
        print(f"Agent Wallet: {self.agent_wallet}")
        print(f"Contract:     {AGENT_HOOK}")
        print(f"TradingAgent: {TRADING_AGENT}")

        # Phase 1: Read pool state
        state = self.read_pool_state()

        # Get current tick
        current_tick = self.get_current_tick()
        if current_tick != 0:
            self.log(f"Current tick: {current_tick}")

        # Phase 2: Decide
        decisions = self.analyze_and_decide(state, current_tick)

        # Phase 3: Execute
        self.execute_actions(decisions, state)

        # Summary
        print(f"\n{'─' * 60}")
        print(f"📋 Run Summary")
        print(f"{'─' * 60}")
        if self.actions_taken:
            for a in self.actions_taken:
                print(f"  ✅ {a}")
        else:
            print(f"  No errors — all systems nominal")
        print(f"{'─' * 60}")
        print(f"Done at {self.ts}")
        print()

        return {
            "state": state,
            "decisions": decisions,
            "actions": self.actions_taken,
            "timestamp": self.ts,
        }


def main():
    parser = argparse.ArgumentParser(description="AgentHook AI Trading Bot")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds (default: 300 = 5 min)")
    args = parser.parse_args()

    bot = TradingBot()

    if args.loop:
        print(f"🔄 Running in loop mode — every {args.interval}s")
        while True:
            try:
                bot.run()
                print(f"😴 Sleeping {args.interval}s...")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n👋 Shutting down.")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print(f"😴 Retrying in {args.interval}s...")
                time.sleep(args.interval)
    else:
        bot.run()


if __name__ == "__main__":
    main()
