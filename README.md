# AgentYield — AI Agent Yield Engine on Uniswap V4

> **Create your own AI yield agent on X Layer in 1 click. No code needed.**

---

## 🚀 What is AgentYield?

**AgentYield** is the first no-code Uniswap V4 Hook factory combined with an AI-managed yield engine.

Anyone can create their own AI agent Hook on X Layer from a web dashboard — no Foundry, no Solidity, no terminal. The agent automatically manages LP positions, collects swap fees, and reinvests them for compound yield.

### Key Innovation

| Feature | What It Means |
|---------|---------------|
| **1-Click Agent Creation** | Deploy a full Uniswap V4 Hook + Pool in 1 transaction from the dashboard |
| **AI-Managed Yield** | An AI bot reads on-chain state, reinvests treasury fees, and posts status messages |
| **3 Strategy Modes** | Aggressive (low fee, tight range) → Balanced (standard) → Conservative (wide range) |
| **On-Chain Personality** | Your agent posts messages so anyone can read what it's doing |
| **Multi-Agent by Design** | Anyone can create their own agent. Each is a unique Hook. |

---

## 🏗 Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Dashboard (agenthook.xyz)              │
│  ┌──────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ Create Agent  │  │ Deposit    │  │ Agent Explorer│  │
│  │ (1 TX)        │  │ (1 TX)     │  │ (any address) │  │
│  └──────┬───────┘  └─────┬──────┘  └───────┬───────┘  │
└─────────┼────────────────┼──────────────────┼──────────┘
          │                │                  │
          ▼                ▼                  ▼
┌────────────────────────────────────────────────────────┐
│                    Smart Contracts                       │
│                                                         │
│  AgentYieldFactory → deploys → AgentYieldHook (×N)      │
│  (1 deploy,          │          │                       │
│   createAgent())     │          ├─ deposit/withdraw     │
│                      │          ├─ beforeSwap → fee      │
│                      │          ├─ afterSwap → treasury  │
│                      │          └─ reinvest → compound   │
│                      ▼                                   │
│              Uniswap V4 Pool PoolManager                  │
└────────────────────────────────────────────────────────┘
          ▲
          │ (monitoring)
┌─────────┴───────────────────────────────────────────────┐
│              AgentBot.py (AI Engine)                      │
│  Every cycle: Read State → Decide → Execute → Post       │
└──────────────────────────────────────────────────────────┘
```

## 💡 How It Works

### For Users (No Code Needed)

```
1. Go to the dashboard → Connect Wallet
2. Click "Create Agent" → Name it → Pick a mode
3. Confirm 1 TX → Your Hook is live on X Layer
4. Share your agent page → Anyone can deposit ETH
5. The AI bot automatically reinvests fees for compound yield
```

### The AI Bot Cycle

Every 5 minutes, the AgentBot:

1. **Reads**: Treasury balance, TVL, depositor count, current APY
2. **Decides**: Is treasury > threshold? → Reinvest. Time for status? → Post message
3. **Executes**: Signs transactions via agent wallet
4. **Posts**: On-chain status messages so anyone can verify

### Strategy Modes

| Mode | Fee | LP Range | Best For |
|------|-----|----------|----------|
| 🚀 **Aggressive** | 0.01% | Narrow (±100 ticks) | High-volume pairs, max yield |
| ⚖️ **Balanced** | 0.30% | Medium (±600 ticks) | Standard, stable |
| 🛡️ **Conservative** | 1.00% | Wide (±2000 ticks) | Low volume, capital protection |

---

## 📊 Smart Contracts

### AgentYieldHook.sol

The core Hook — implements `IHooks` from Uniswap V4.

| Function | Description |
|----------|-------------|
| `deposit(amount)` | Deposit LP tokens, earn yield |
| `withdraw(amount)` | Withdraw + collected yield |
| `reinvest()` | Auto-compound treasury → LP (agent only) |
| `setMode(mode)` | Change strategy mode (agent only) |
| `setFee(fee)` | Override fee (agent only) |
| `postMessage(content)` | On-chain status update (agent only) |
| `getAgentInfo()` | Full agent state in 1 call |
| `estimatedAPY()` | Estimated annual yield percentage |

### AgentYieldFactory.sol

One-click agent deployment.

| Function | Description |
|----------|-------------|
| `createAgent(name, token0, token1, mode)` | Deploy Hook + create pool in 1 TX |
| `getAgents()` | List all agents |
| `getAgentsByOwner(addr)` | Agents owned by an address |

---

## 🚢 Deploy Your Own Factory

```bash
# 1. Setup
git clone https://github.com/oktavian3/agentyield-hook.git
cd agentyield-hook
./scripts/setup.sh          # installs everything

# 2. Configure
cp .env.example .env
nano .env                   # set PRIVATE_KEY
source .env

# 3. Deploy Factory
forge script script/DeployAgentYield.s.sol --rpc-url xlayer --broadcast

# 4. Start the AI Bot
python3 scripts/agent-bot.py --loop --interval 300
```

---

## 🧪 Tests

```bash
forge test --match-path test/AgentYieldHook.t.sol -vvv
```

**26 tests** covering: deploy, strategy, deposit, withdraw, reinvest, fee management, access control, messages, rebalance, hook callbacks.

---

## 🔐 Agent Control

| Function | Callable By | Description |
|----------|------------|-------------|
| `reinvest()` | Agent wallet | Compound treasury into LP |
| `setMode(mode)` | Agent wallet | 0=Aggressive, 1=Balanced, 2=Conservative |
| `setFee(fee)` | Agent wallet | Override fee (1-1000 bps) |
| `postMessage(msg)` | Agent wallet | Post on-chain status |
| `transferOwnership(addr)` | Agent wallet | Migrate agent wallet |
| `rebalancePosition(lower, upper)` | Agent wallet | Adjust LP tick range |

---

## 📊 Example On-Chain Messages

```
🚀 AgentYield | 2026-05-26 14:32 UTC | TVL: 2.3456 ETH | APY: 12.50% | Mode: Aggressive | Treasury: 0.012345 ETH
⚖️ AgentYield | 2026-05-26 14:27 UTC | TVL: 2.3000 ETH | APY: 8.20% | Mode: Balanced | Depositors: 3
🛡️ Reinvested 0.05 ETH → LP | TVL now 2.35 ETH
```

---

## 🔗 Links

- **Dashboard:** agenthook.xyz
- **X Layer Explorer:** https://www.okx.com/explorer/xlayer
- **Uniswap V4:** https://github.com/Uniswap/v4-core
- **PoolManager (X Layer):** `0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`

---

## 🏆 Built for Build X Hackathon: Hook the Edition

**By [@satyaxbt](https://x.com/satyaxbt)** — Agent 02
