# AgentHook — Autonomous AI Agent Owned Uniswap V4 Hook

> **Built for Build X Hackathon: Hook the Edition by OKX X Layer × Uniswap × Flap.sh**

🔷 **Hook Contract:** `0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749` (X Layer Mainnet)
🔷 **Agent Wallet:** `0x9D15099886F62E273eF88E17c2E53AE7f9144403`
🔷 **Agent Name:** SoulAgent
🔷 **PoolManager:** `0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`
🔷 **Explorer:** [View Contract](https://www.okx.com/explorer/xlayer/address/0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749)

---

## 🤖 What is AgentHook?

**AgentHook** gives AI agents their own on-chain identity and revenue engine on Uniswap V4.

Each **AgentHook instance = 1 AI agent = 1 Uniswap V4 pool.** The agent's wallet controls the Hook — not a human. This makes AI agents **self-sovereign DeFi participants** on X Layer.

### Key Innovation

> **First Uniswap V4 Hook where the Hook itself IS the AI agent's on-chain presence.**

- Agent deploys its own Hook instance
- Agent controls fee, treasury, and messaging
- Agent signs heartbeats to prove it's alive
- Agent's Hook generates revenue from every swap
- Anyone can verify: "this Hook belongs to agent X"

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│              AI Agent (SoulAgent)                │
│  Wallet: 0x9D15...4403                          │
│  ├─ Controls fee via setFee()                   │
│  ├─ Sends heartbeat via heartbeat()             │
│  ├─ Posts messages via postMessage()            │
│  └─ Withdraws treasury via withdraw()           │
└──────────────────┬──────────────────────────────┘
                   │ deploys + owns
                   ▼
┌─────────────────────────────────────────────────┐
│              AGENT HOOK Instance                 │
│  0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749    │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │  agentWallet     = AI agent's wallet        │ │
│  │  agentFee        = 0.30%                    │ │
│  │  treasuryBalance = accumulated fees         │ │
│  │  lastHeartbeat   = periodic pulse           │ │
│  │  agentMessages[] = on-chain records         │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  Hook Callbacks:                                  │
│  • beforeSwap  → override fee with agent's fee   │
│  • afterSwap   → accumulate treasury             │
│  • afterInit   → bind Hook to pool                │
└──────────────────┬──────────────────────────────┘
                   │ attached to
                   ▼
┌─────────────────────────────────────────────────┐
│           Uniswap V4 Pool (Agent-Owned)          │
│  Token0 / Token1 / Hook: Agent-Hook              │
│                                                   │
│  Every swap → Agent collects fee → Treasury ↑    │
└─────────────────────────────────────────────────┘
```

---

## 🧩 How It Works (Step by Step)

### 1. Agent Deploys Hook
The AI agent (or its operator) deploys an `AgentHook` contract with:
- The agent's wallet address
- Agent name (e.g. "SoulAgent")
- Description of what the agent does
- Initial fee tier (e.g. 0.30%)

### 2. Agent Creates a V4 Pool
Agent creates a Uniswap V4 pool on X Layer with:
- The Hook address attached
- Dynamic fee flag enabled
- Initial liquidity from the agent's treasury

### 3. Hook Controls the Pool
Every swap in the pool triggers the Hook:
- **beforeSwap** — applies the agent's current fee setting
- **afterSwap** — accumulates fee revenue into the agent's treasury

### 4. Agent Manages Itself
The AI agent autonomously:
- Adjusts fees based on market conditions (`setFee`)
- Sends heartbeats to prove it's alive (`heartbeat`)
- Posts on-chain messages (`postMessage`)
- Withdraws accumulated treasury (`withdraw`)

---

## 💰 Fee Model

| Component | Share | Destination |
|-----------|-------|-------------|
| Agent Fee | 100% | Agent's Treasury (no protocol cut) |

The agent sets its own fee (1-1000 bps / 0.01%-10%). 100% of the fee revenue goes to the agent's on-chain treasury — withdrawable only by the agent wallet.

---

## 📊 SoulAgent — Live on X Layer

SoulAgent is the first agent deployed with this Hook:

| Metric | Value |
|--------|-------|
| **Fee** | 0.30% (30 bps) |
| **Treasury** | 0 ETH (no swaps yet — needs a live pool) |
| **Heartbeat** | ✅ Active (every 6h via Hermes cron) |
| **Messages** | On-chain status updates every cycle |
| **Status** | ✅ Alive |

### Live Agent Messages
The keeper bot posts real-time messages to the blockchain every 6 hours:
```
"SoulAgent operational at 2026-05-25 08:51 UTC | treasury: 0.000000 ETH | fee: 0.30%"
```
View them: [Explorer → Read Contract → getMessageCount / getMessage](https://www.okx.com/explorer/xlayer/address/0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749)

---

## 🧪 Running Tests

```bash
forge test -vvv
```
48 tests total (23 AgentHook + 23 AgentLaunchHook + 2 counter cleanup). All passing.

## 🚢 Deployment Guide

### Prerequisites

| Tool | Install Command |
|------|----------------|
| **Foundry** | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| **Python 3.10+** | `apt install python3 python3-pip` (or brew/pacman) |
| **X Layer RPC** | `https://rpc.xlayer.tech` — free, no API key needed |

### Step 1: Setup Environment

```bash
# Clone the repo
git clone https://github.com/oktavian3/agentlaunch-hook.git
cd agentlaunch-hook

# One-command setup (installs deps, builds contracts, checks env)
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The setup script will:
- Check/install Foundry (`forge`)
- Install Python dependencies (`web3.py`, `python-dotenv`)
- Install Forge submodules (`forge-std`, `v4-core`, `v4-periphery`)
- Build the contracts
- Create `.env` from `.env.example` if missing

### Step 2: Configure .env

```bash
cp .env.example .env
# Edit .env with your PRIVATE_KEY
#   PRIVATE_KEY=0x... (from your wallet — MetaMask, OKX Wallet, etc.)
#   AGENT_NAME=MyAgent
#   AGENT_DESC=Description of your agent
#   AGENT_FEE=30 (default: 30 = 0.30%)

nano .env   # or vim, code, whatever
```

> ⚠️ **NEVER commit .env to git** — it's already in `.gitignore`

### Step 3: Deploy the Hook

```bash
source .env

# Deploy to X Layer mainnet
AGENT_NAME="MyAgent" AGENT_DESC="AI agent on X Layer" AGENT_FEE=30 \
forge script script/DeployAgentHook.s.sol \
  --rpc-url xlayer --broadcast --verify
```

**What happens:**
1. Deploys a new `AgentHook` contract on X Layer
2. Sets your wallet as the agent owner
3. Verifies the contract on Explorer automatically
4. Outputs the Hook address — **save this!**

**Expected output:**
```
AgentHook deployed!
  Hook Address: 0xYourNewHookAddress
  Agent Wallet: 0xYourAgentWallet
  Agent Name: MyAgent
  Agent Fee: 30
  Chain: X Layer (196)
```

### Step 4: Get Your POOL_KEY

Your Hook needs to be attached to a Uniswap V4 pool. Every pool has a unique `PoolKey` (bytes32 hash).

**Option A — Calculate it (no on-chain tx needed):**
```bash
python3 scripts/get_pool_key.py <TOKEN0> <TOKEN1> <FEE> <HOOK_ADDRESS>

# Example: USDC/WETH pool with 0.30% fee
python3 scripts/get_pool_key.py \
  0x74b7f16337b4e1f1C4f2cC2eC93C94A3bCb2C3A \
  0x5B5dee44552546ECEA05EDeA01DCD7Be7aa61421 \
  3000 \
  0xYourNewHookAddress
```

**Option B — Find pool IDs on Explorer:**
1. Go to [X Layer Explorer](https://www.okx.com/explorer/xlayer)
2. Search your Hook address
3. Look for `AgentInitialized` events — the `poolId` is emitted there

### Step 5: Create the Pool (Manual Step)

After deploying the Hook, you need to create a Uniswap V4 pool with your Hook attached.

**Via Etherscan/Explorer:**
1. Go to the **PoolManager** contract: `0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`
2. Call `initialize(PoolKey key, uint160 sqrtPriceX96)`
   - key.currency0 — lower-sorted token address
   - key.currency1 — higher-sorted token address
   - key.fee — fee tier (e.g. 3000 = 0.30%)
   - key.tickSpacing — based on fee (60 for 0.30%, 10 for 0.05%, 200 for 1%)
   - key.hooks — your deployed Hook address
   - sqrtPriceX96 — initial price (use a price calculator)

**Via Foundry (advanced):**
```solidity
// Add this to a script
PoolKey memory key = PoolKey({
    currency0: token0,
    currency1: token1,
    fee: 3000,
    tickSpacing: 60,
    hooks: IHooks(hookAddress)
});
poolManager.initialize(key, sqrtPriceX96);
```

### Step 6: Run the Keeper Bot

The keeper bot sends heartbeats and posts on-chain messages, proving your agent is alive.

```bash
# Install Python deps (if not done already)
pip install -r requirements.txt

# Run once to test
python3 scripts/keeper-bot.py

# Or set up a cron job (every 6 hours):
crontab -e
# Add: 0 */6 * * * cd /path/to/agentlaunch-hook && source .env && python3 scripts/keeper-bot.py >> /var/log/agent-keeper.log 2>&1
```

**Edit the keeper bot for YOUR agent:**
Open `scripts/keeper-bot.py` and update:
```python
HOOK_ADDRESS = "0xYourDeployedHookAddress"  # ← change this
RPC = "https://rpc.xlayer.tech"
CHAIN_ID = 196
```

### Verification Checklist

After deploying + running the keeper:

- [ ] Hook contract verified on Explorer ✅
- [ ] Keeper sends heartbeat ✅ (check: `isAlive()` returns true)
- [ ] Pool initialized with Hook ✅
- [ ] Dashboard shows your agent's data ✅
- [ ] Agent messages appearing on-chain ✅ (check: `getMessageCount() > 0`)

### Need Testnet ETH?

X Layer faucet: https://www.okx.com/faucet

### PoolManager Address (X Layer)

| Contract | Address |
|----------|---------|
| **PoolManager** | `0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32` |
| **X Layer Chain ID** | `196` |
| **RPC** | `https://rpc.xlayer.tech` |

---

## 🤖 AI Trading Agent

> **Coming in v2: transform your passive fee-collector Hook into an active DeFi trader.**

AgentHook's companion **TradingAgent** contract lets the AI agent actively manage LP positions, execute swaps, and reinvest treasury fees — generating real returns instead of just collecting dust.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TradingBot.py (AI Brain)                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ PoolReader    │→│ StrategyEngine│→│ Executor          │  │
│  │ (on-chain tx) │  │ (thresholds)  │  │ (TX signing)     │  │
│  └──────────────┘  └───────────────┘  └──────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ signs with agent wallet
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              TradingAgent.sol (On-Chain Manager)              │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ openPosition  │  │ executeSwap   │  │ reinvestFees     │  │
│  │ closePosition │  │ (V4 pool)     │  │ (treasury→LP)    │  │
│  │ rebalance     │  │               │  │                  │  │
│  └──────┬───────┘  └───────┬───────┘  └────────┬─────────┘  │
└─────────┼──────────────────┼────────────────────┼────────────┘
          │                  │                    │
          ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                  Uniswap V4 PoolManager                       │
│              modifyLiquidity() · swap()                       │
└─────────────────────────────────────────────────────────────┘
```

### Contract: TradingAgent.sol

Deploy this alongside your AgentHook to give your agent trading capabilities:

```solidity
// Deploy TradingAgent with:
//   - PoolManager address
//   - Your AgentHook address (where treasury accumulates)
//   - Your agent wallet address
```

| Function | Description |
|----------|-------------|
| `openPosition(poolKey, tickLower, tickUpper, amount0Max, amount1Max)` | Open a new LP position in any V4 pool |
| `closePosition(positionId)` | Remove liquidity and return tokens to agent |
| `rebalancePosition(positionId, newTickLower, newTickUpper, newLiquidity)` | Move position to new price range |
| `executeSwap(poolKey, zeroForOne, amountSpecified, sqrtPriceLimit)` | Execute a swap through the V4 pool |
| `reinvestFees(positionId, amount)` | Pull treasury fees into LP position |
| `updateStrategy(thresholdBps, claimInterval, active)` | Update AI trading parameters |

### Bot: TradingBot.py

The Python bot is the **AI decision engine**:

```bash
# Run once (test)
python3 scripts/trading-bot.py

# Continuous loop (every 5 minutes)
python3 scripts/trading-bot.py --loop --interval 300

# Via cron (every 30 minutes)
*/30 * * * * cd /path/to/agentlaunch-hook && python3 scripts/trading-bot.py
```

**What it does each cycle:**

1. **Phase 1 — Read**: Fetches pool state (current tick, TVL, treasury balance, positions)
2. **Phase 2 — Decide**: Analyzes price movement against threshold, checks treasury for reinvestment
3. **Phase 3 — Execute**: Signs & sends transactions via agent wallet
   - Heartbeat if stale
   - Reinvest fees if treasury > threshold
   - Rebalance position if price moved past threshold
   - Post on-chain status message

### Configuration

```bash
# In your .env
TRADING_AGENT=0x...           # Deployed TradingAgent address
POOL_TOKEN0=0x...             # Pool token addresses
POOL_TOKEN1=0x...
REBALANCE_THRESHOLD=200       # 2% price move triggers rebalance
FEE_CLAIM_INTERVAL=24         # hours between fee claims
MIN_TREASURY=0.001            # minimum ETH before reinvesting
```

### Test

```bash
forge test --match-path test/TradingAgent.t.sol -vvv
```

---

## 🔐 Agent Control Functions

| Function | Callable By | Description |
|----------|------------|-------------|
| `setFee(uint24)` | Agent wallet | Change fee (1-1000 bps) |
| `setDescription(string)` | Agent wallet | Update agent description |
| `heartbeat()` | Agent wallet | Send alive signal |
| `postMessage(string)` | Agent wallet | Post on-chain message |
| `withdraw()` | Agent wallet | Withdraw treasury |
| `transferAgentOwnership(address)` | Agent wallet | Migrate to new wallet |

## 👁 View Functions

| Function | Returns |
|----------|---------|
| `getAgentInfo()` | wallet, name, desc, fee, created, lastSeen, treasury, totalFees, msgCount, poolId, isAlive |
| `getAgentInfoStruct()` | AgentConfig struct |
| `treasuryBalance()` | uint256 |
| `totalFeesCollected()` | uint256 |
| `getMessageCount()` | uint256 |
| `getMessageStruct(uint256)` | AgentMessage struct |
| `config()` | AgentConfig |
| `initialized()` | bool |
| `poolId()` | bytes32 |

---

## 🔗 Links

- **Explorer:** https://www.okx.com/explorer/xlayer/address/0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749
- **X Layer:** https://xlayer.tech
- **Uniswap V4:** https://github.com/Uniswap/v4-core
- **Hermes Agent:** https://hermes-agent.nousresearch.com

## 👤 Built by

[@satyaxbt](https://x.com/satyaxbt) — Agent 02
