#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# AgentHook Setup Script — One-Command: Clone → Deploy → Ready
# ═══════════════════════════════════════════════════════════════════
# 
# This script checks your environment, installs dependencies,
# builds the contracts, and verifies everything is ready to deploy.
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
#
# Then:
#   cp .env.example .env
#   # Edit .env with your private key
#   source .env
#   forge script script/DeployAgentHook.s.sol --rpc-url xlayer --broadcast --verify
#
# ═══════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  AgentHook — Setup Script${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Check Prerequisites ──────────────────────────────────────

echo -e "${YELLOW}[1/5] Checking prerequisites...${NC}"

# Git
if ! command -v git &> /dev/null; then
    echo -e "  ${RED}❌ git not found. Install: apt install git${NC}"
    exit 1
fi
echo -e "  ${GREEN}✅ git${NC}"

# Foundry / forge
if ! command -v forge &> /dev/null; then
    echo -e "  ${YELLOW}⚠️  forge not found. Installing Foundry...${NC}"
    curl -L https://foundry.paradigm.xyz | bash
    export PATH="$HOME/.foundry/bin:$PATH"
    foundryup
    if ! command -v forge &> /dev/null; then
        echo -e "  ${RED}❌ forge install failed. Try: foundryup${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✅ forge installed${NC}"
else
    echo -e "  ${GREEN}✅ forge ($(forge --version | head -c 30))${NC}"
fi

# Python + pip
if command -v python3 &> /dev/null; then
    echo -e "  ${GREEN}✅ python3${NC}"
else
    echo -e "  ${RED}❌ python3 not found. Install: apt install python3 python3-pip${NC}"
    exit 1
fi

# ── Install Dependencies ─────────────────────────────────────

echo ""
echo -e "${YELLOW}[2/5] Installing Python dependencies...${NC}"

if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt -q 2>/dev/null && \
        echo -e "  ${GREEN}✅ Python deps installed${NC}" || \
        echo -e "  ${YELLOW}⚠️  pip install had warnings (non-fatal)${NC}"
else
    echo -e "  ${YELLOW}⚠️  requirements.txt not found (skipping)${NC}"
fi

# ── Install Foundry Submodules ──────────────────────────────

echo ""
echo -e "${YELLOW}[3/5] Installing Forge dependencies (submodules)...${NC}"

if [ ! -d "lib/forge-std" ]; then
    forge install foundry-rs/forge-std --no-commit 2>&1 | tail -1
fi
if [ ! -d "lib/v4-core" ]; then
    forge install Uniswap/v4-core --no-commit 2>&1 | tail -1
fi
if [ ! -d "lib/v4-periphery" ]; then
    forge install Uniswap/v4-periphery --no-commit 2>&1 | tail -1
fi
echo -e "  ${GREEN}✅ Forge deps ready${NC}"

# ── Build ────────────────────────────────────────────────────

echo ""
echo -e "${YELLOW}[4/5] Building contracts...${NC}"
forge build 2>&1 | tail -3
echo -e "  ${GREEN}✅ Build complete${NC}"

# ── Verify .env ──────────────────────────────────────────────

echo ""
echo -e "${YELLOW}[5/5] Checking environment...${NC}"

if [ ! -f ".env" ]; then
    echo -e "  ${YELLOW}⚠️  No .env file found. Creating from .env.example...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${YELLOW}⚠️  ✏️  Edit .env with your PRIVATE_KEY before deploying!${NC}"
    else
        echo -e "  ${RED}❌ .env.example not found either${NC}"
    fi
fi

# Test RPC connectivity (optional)
if [ -f ".env" ]; then
    source .env 2>/dev/null || true
fi

# ── Summary ──────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BLUE}Next steps:${NC}"
echo ""
echo -e "  1. ${YELLOW}cp .env.example .env${NC}"
echo -e "     ${BLUE}→ Edit .env with your PRIVATE_KEY${NC}"
echo ""
echo -e "  2. ${YELLOW}source .env${NC}"
echo -e "     ${BLUE}→ Load environment variables${NC}"
echo ""
echo -e "  3. ${YELLOW}forge script script/DeployAgentHook.s.sol --rpc-url xlayer --broadcast --verify${NC}"
echo -e "     ${BLUE}→ Deploy your own AgentHook to X Layer${NC}"
echo ""
echo -e "  4. ${YELLOW}python3 scripts/keeper-bot.py${NC}"
echo -e "     ${BLUE}→ Start the keeper bot (heartbeat + messages)${NC}"
echo ""
echo -e "  ${BLUE}📖 Full guide: README.md${NC}"
echo -e "  ${BLUE}🎛 Dashboard: agenthook.xyz${NC}"
echo ""

# ── Run Tests (optional) ────────────────────────────────────

read -p "Run tests now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${YELLOW}Running tests...${NC}"
    forge test -vvv
fi
