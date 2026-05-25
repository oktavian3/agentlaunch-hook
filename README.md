# AgentLaunch — AI Agent Token Launchpad

> **Built for Build X Hackathon: Hook the Edition by OKX X Layer × Uniswap × Flap.sh**

🔷 **Hook Contract:** `0x6dC1E204B54C231A5e3dc2F0A1418649c079eCAf` (X Layer Mainnet)
🔷 **PoolManager:** `0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`
🔷 **Dashboard:** [agentlaunch-hook.vercel.app](https://agentlaunch-hook.vercel.app)
🔷 **Explorer:** [View Contract](https://www.okx.com/explorer/xlayer/address/0x6dC1E204B54C231A5e3dc2F0A1418649c079eCAf)

## 🚀 What is AgentLaunch?

**AgentLaunch** is a Uniswap V4 Hook that enables anyone to launch an AI agent token with:
- **Built-in bonding curve** — linear price discovery (early buyers get better prices)
- **Automated fee distribution** — 70% LP / 20% Dev / 10% Protocol
- **On-chain metadata registry** — name, symbol, personality, social links
- **Agent personality stored on-chain** — every token describes its AI agent

### How It Works
1. Anyone creates a Uniswap V4 pool on X Layer with this Hook address
2. The Hook auto-registers the pool as an agent token
3. The pool creator configures metadata (name, symbol, personality)
4. Swap fees are automatically split: LP (70%), Creator (20%), Protocol (10%)
5. Bonding curve tracks supply to determine token price

### Contract Architecture

```
afterInitialize()    → Register agent in global registry
beforeSwap()         → Apply agent-specific fee with bonding curve adjustment
afterSwap()          → Distribute fees (dev share + protocol share)
afterAddLiquidity()  → Track supply increase → update bonding curve
afterRemoveLiquidity() → Track supply decrease → update bonding curve
```

### Fee Model

| Share | Percentage | Recipient |
|-------|-----------|-----------|
| 🟢 LP Fee | 70% | Liquidity Providers |
| 🟣 Dev Share | 20% | Agent Creator (withdrawable) |
| 🔵 Protocol | 10% | Hook Owner (global treasury) |

### Bonding Curve

```
price = basePrice + (currentSupply / maxSupply) × priceRange
```

- **basePrice:** 0.000000001 ETH
- **maxSupply:** 1B tokens
- **priceRange:** 0.001 ETH
- Fee adjusts slightly based on fill ratio — higher in early discovery, lower near cap

## 🛠 Tech Stack

- **Solidity 0.8.26** — AgentLaunchHook contract
- **Foundry** — Build, test, deploy
- **Uniswap V4** — PoolManager + IHooks interface
- **X Layer** — Chain ID 196
- **Ethers.js** — Dashboard frontend

## 📦 Project Structure

```
├── src/
│   └── AgentLaunchHook.sol    # Main Hook contract
├── test/
│   └── AgentLaunchHook.t.sol  # 23 unit tests (all passing)
├── script/
│   └── DeployAgentLaunchHook.s.sol  # Deploy script
├── dashboard/
│   └── index.html             # Dashboard UI
├── vercel.json                # Vercel config
├── foundry.toml               # Foundry config
└── README.md
```

## 🧪 Running Tests

```bash
forge test -vvv
```

## 🚢 Deployment

```bash
source .env
forge script script/DeployAgentLaunchHook.s.sol \
  --rpc-url xlayer --broadcast --verify
```

### PoolManager on X Layer
`0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32`

## 🔗 Links

- **Dashboard:** https://agentlaunch-hook.vercel.app
- **Contract:** https://www.okx.com/explorer/xlayer/address/0x6dC1E204B54C231A5e3dc2F0A1418649c079eCAf
- **X Layer:** https://xlayer.tech
- **Uniswap V4:** https://github.com/Uniswap/v4-core

## 👤 Built by

[@satyaxbt](https://x.com/satyaxbt) — Agent 02
