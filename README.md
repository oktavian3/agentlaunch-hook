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

## 🚢 Deployment

```bash
source .env

# Deploy a new AgentHook for any AI agent
AGENT_NAME="MyAgent" AGENT_DESC="Description" AGENT_FEE=30 \
forge script script/DeployAgentHook.s.sol \
  --rpc-url xlayer --broadcast --verify
```

### PoolManager Address (X Layer)
`0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`

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
