#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# AgentYield — 1-Click Setup
# ═══════════════════════════════════════════════════════════════
# Usage: chmod +x scripts/setup.sh && ./scripts/setup.sh
# ═══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  AgentYield — Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check Foundry
if ! command -v forge &> /dev/null; then
    echo -e "${YELLOW}Installing Foundry...${NC}"
    curl -L https://foundry.paradigm.xyz | bash
    export PATH="$HOME/.foundry/bin:$PATH"
    foundryup
fi
echo -e "  ${GREEN}✅ forge ($(forge --version | head -c 20))${NC}"

# Install deps
if [ ! -d "lib/forge-std" ]; then
    forge install foundry-rs/forge-std --no-commit 2>&1 | tail -1
fi
if [ ! -d "lib/v4-core" ]; then
    forge install Uniswap/v4-core --no-commit 2>&1 | tail -1
fi
echo -e "  ${GREEN}✅ Forge deps${NC}"

# Python deps
pip3 install -r requirements.txt -q 2>/dev/null || true
echo -e "  ${GREEN}✅ Python deps${NC}"

# Build
forge build --contracts new-contracts/AgentYieldHook.sol 2>&1 | tail -1
echo -e "  ${GREEN}✅ Build${NC}"

# Tests
echo ""
echo -e "${YELLOW}Run tests? (y/N)${NC} \c"
read -n1 yn; echo
if [[ $yn =~ [Yy] ]]; then
    forge test --match-path test/AgentYieldHook.t.sol -vvv
fi

# Env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ${YELLOW}⚠️  Created .env — edit with your PRIVATE_KEY${NC}"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Setup Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Next:"
echo "  1. Edit .env → set PRIVATE_KEY"
echo "  2. source .env"
echo "  3. forge script script/DeployAgentYield.s.sol --rpc-url xlayer --broadcast"
echo "  4. Set FACTORY_ADDRESS in .env"
echo "  5. python3 scripts/agent-bot.py"
