// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test, console} from "forge-std/Test.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {BalanceDelta} from "v4-core/types/BalanceDelta.sol";
import {AgentYieldHook} from "../src/AgentYieldHook.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";

contract AgentYieldHookTest is Test {
    AgentYieldHook public hook;

    address public agentWallet = address(0x42);
    address public user1 = address(0x101);
    address public user2 = address(0x102);
    address public deployer = address(0x1);
    IPoolManager public poolManager = IPoolManager(address(0x100));

    function setUp() public {
        vm.deal(user1, 10000 ether);
        vm.deal(user2, 10000 ether);
        vm.prank(deployer);
        hook = new AgentYieldHook(poolManager, agentWallet, "TestYieldAgent", AgentYieldHook.StrategyMode.Balanced);
    }

    // Helper: deposit with ETH
    function _deposit(address user, uint256 amount) internal {
        vm.deal(user, amount);
        vm.prank(user);
        hook.deposit{value: amount}(amount);
    }

    // ============================================================
    // Deploy
    // ============================================================

    function test_Deploy() public {
        assertEq(hook.agentName(), "TestYieldAgent");
        assertEq(hook.agentWallet(), agentWallet);
        assertTrue(hook.alive());
        assertEq(address(hook.poolManager()), address(poolManager));
        assertEq(uint8(hook.mode()), uint8(AgentYieldHook.StrategyMode.Balanced));
    }

    // ============================================================
    // Strategy / Mode
    // ============================================================

    function test_DefaultMode_Balanced() public {
        assertEq(uint8(hook.mode()), uint8(AgentYieldHook.StrategyMode.Balanced));
        assertEq(hook.fee(), 30);
    }

    function test_ModeSet_Aggressive() public {
        vm.prank(agentWallet);
        hook.setMode(AgentYieldHook.StrategyMode.Aggressive);
        assertEq(uint8(hook.mode()), uint8(AgentYieldHook.StrategyMode.Aggressive));
        assertEq(hook.fee(), 1);
    }

    function test_ModeSet_Conservative() public {
        vm.prank(agentWallet);
        hook.setMode(AgentYieldHook.StrategyMode.Conservative);
        assertEq(uint8(hook.mode()), uint8(AgentYieldHook.StrategyMode.Conservative));
        assertEq(hook.fee(), 100);
    }

    // ============================================================
    // Deposit
    // ============================================================

    function test_Deposit() public {
        _deposit(user1, 100 ether);

        (uint256 amount,) = hook.getDepositorInfo(user1);
        assertEq(amount, 99.9 ether);
        assertEq(hook.totalDeposits(), 99.9 ether);
    }

    function test_DepositTwoUsers() public {
        _deposit(user1, 100 ether);

        _deposit(user2, 50 ether);

        assertEq(hook.getDepositorCount(), 2);
        assertEq(hook.totalDeposits(), 149.85 ether);
        assertEq(hook.treasuryBalance(), 0.15 ether);
    }

    function test_Deposit_RevertsOnZero() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: zero amount"));
        hook.deposit(0);
    }

    // ============================================================
    // Withdraw
    // ============================================================

    function test_Withdraw() public {
        _deposit(user1, 100 ether);

        vm.prank(user1);
        hook.withdraw(0);

        (uint256 remaining,) = hook.getDepositorInfo(user1);
        assertEq(remaining, 0);
    }

    function test_Withdraw_RevertsOnNoDeposit() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: no deposit"));
        hook.withdraw(0);
    }

    function test_Withdraw_RevertsOnExcess() public {
        _deposit(user1, 100 ether);

        vm.prank(user1);
        vm.expectRevert(bytes("AY: exceeds balance"));
        hook.withdraw(200 ether);
    }

    // ============================================================
    // Agent Controls
    // ============================================================

    function test_SetFee() public {
        vm.prank(agentWallet);
        hook.setFee(50);
        assertEq(hook.fee(), 50);
    }

    function test_SetFee_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.setFee(50);
    }

    function test_SetMode_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.setMode(AgentYieldHook.StrategyMode.Aggressive);
    }

    function test_PostMessage() public {
        vm.prank(agentWallet);
        hook.postMessage("Hello from the agent!");

        assertEq(hook.getMessageCount(), 1);
        assertEq(hook.getMessage(0), "Hello from the agent!");
    }

    function test_PostMessage_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.postMessage("test");
    }

    function test_TransferOwnership() public {
        address newWallet = address(0xCAFE);
        vm.prank(agentWallet);
        hook.transferOwnership(newWallet);
        assertEq(hook.agentWallet(), newWallet);
    }

    function test_RebalancePosition() public {
        vm.prank(agentWallet);
        hook.rebalancePosition(-500, 500);
        assertEq(hook.currentTickLower(), -500);
        assertEq(hook.currentTickUpper(), 500);
    }

    function test_RebalancePosition_RevertsOnInvalidTicks() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AY: invalid ticks"));
        hook.rebalancePosition(500, -500);
    }

    function test_SetAlive() public {
        vm.prank(agentWallet);
        hook.setAlive(false);
        assertFalse(hook.alive());

        vm.prank(agentWallet);
        hook.setAlive(true);
        assertTrue(hook.alive());
    }

    function test_SetAlive_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.setAlive(false);
    }

    // ============================================================
    // Treasury & Reinvest
    // ============================================================

    function test_DepositCreatesTreasury() public {
        _deposit(user1, 1000 ether);
        assertTrue(hook.treasuryBalance() > 0);
        assertEq(hook.treasuryBalance(), 1 ether);
    }

    function test_Reinvest() public {
        _deposit(user1, 100 ether);
        assertTrue(hook.treasuryBalance() > 0);

        vm.warp(block.timestamp + hook.REINVEST_COOLDOWN() + 1);

        vm.prank(agentWallet);
        hook.reinvest();
        assertEq(hook.treasuryBalance(), 0);
    }

    function test_Reinvest_RevertsFromNonAgent() public {
        _deposit(user1, 100 ether);
        vm.warp(block.timestamp + hook.REINVEST_COOLDOWN() + 1);
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.reinvest();
    }

    function test_Reinvest_RevertsOnEmpty() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AY: empty treasury"));
        hook.reinvest();
    }

    function test_Reinvest_RevertsOnCooldown() public {
        _deposit(user1, 100 ether);
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AY: cooldown"));
        hook.reinvest();
    }

    // ============================================================
    // Treasury Deposit (AI bot simulates swap fees)
    // ============================================================

    function test_DepositTreasury() public {
        vm.prank(agentWallet);
        hook.depositTreasury(5 ether);

        assertEq(hook.treasuryBalance(), 5 ether);
        assertEq(hook.totalFeesCollected(), 5 ether);
    }

    function test_DepositTreasury_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.depositTreasury(1 ether);
    }

    // ============================================================
    // View Functions
    // ============================================================

    function test_GetAgentInfo() public {
        (string memory name, address wallet, uint256 tvl, uint256 treasury,
         uint256 totalFees, uint256 depCount, uint256 msgCount,
         uint8 _mode, uint24 _fee, uint128 liq, bool alive) = hook.getAgentInfo();

        assertEq(name, "TestYieldAgent");
        assertEq(wallet, agentWallet);
        assertEq(tvl, 0);
        assertEq(treasury, 0);
        assertEq(totalFees, 0);
        assertEq(depCount, 0);
        assertEq(msgCount, 0);
        assertEq(_mode, uint8(AgentYieldHook.StrategyMode.Balanced));
        assertEq(_fee, 30);
        assertEq(liq, 0);
        assertTrue(alive);
    }

    // ============================================================
    // Simulate Swap Fee Tests
    // ============================================================

    function test_SimulateSwapFee() public {
        _deposit(user1, 10 ether);
        uint256 feeAmount = 0.01 ether; // 0.1% of 10 ETH
        vm.prank(agentWallet);
        hook.simulateSwapFee(feeAmount);

        assertEq(hook.totalFeesCollected(), feeAmount);
        assertEq(hook.treasuryBalance(), (10 ether * 10) / 10000 + feeAmount); // deposit fee + sim fee
    }

    function test_SimulateSwapFee_RevertsFromNonAgent() public {
        _deposit(user1, 10 ether);
        vm.prank(user1);
        vm.expectRevert("AY: not agent");
        hook.simulateSwapFee(0.01 ether);
    }

    function test_SimulateSwapFee_RevertsOnZero() public {
        _deposit(user1, 10 ether);
        vm.prank(agentWallet);
        vm.expectRevert("AY: zero amount");
        hook.simulateSwapFee(0);
    }

    function test_SimulateSwapFee_RevertsOnExcessive() public {
        _deposit(user1, 10 ether);
        vm.prank(agentWallet);
        vm.expectRevert("AY: fee too large");
        hook.simulateSwapFee(0.5 ether); // 5% > max 1%
    }

    function test_SimulateSwapFee_UpdatesAPY() public {
        _deposit(user1, 10 ether);
        vm.warp(block.timestamp + 1 days);

        vm.prank(agentWallet);
        hook.simulateSwapFee(0.01 ether); // 0.1% fee on 10 ETH

        uint256 apy = hook.estimatedAPY();
        assertTrue(apy > 0, "APY should be > 0 after simulated fees");
    }

    function test_GetMessages() public {
        vm.prank(agentWallet);
        hook.postMessage("msg1");
        vm.prank(agentWallet);
        hook.postMessage("msg2");

        assertEq(hook.getMessageCount(), 2);
        assertEq(hook.getMessage(0), "msg1");
        assertEq(hook.getMessage(1), "msg2");
    }

    function test_Deposit_DisallowsWhenDead() public {
        vm.prank(agentWallet);
        hook.setAlive(false);

        vm.expectRevert(bytes("AY: not alive"));
        vm.prank(user1);
        hook.deposit{value: 100 ether}(100 ether);
    }

    // ============================================================
    // Hook Callbacks
    // ============================================================

    function test_BeforeInitialize_ReturnsSelector() public {
        PoolKey memory key = PoolKey({
            currency0: Currency.wrap(address(0x1)),
            currency1: Currency.wrap(address(0x2)),
            fee: 30,
            tickSpacing: 60,
            hooks: hook
        });
        vm.prank(address(poolManager));
        bytes4 selector = hook.beforeInitialize(address(0), key, 0);
        assertEq(selector, hook.beforeInitialize.selector);
    }

    // ============================================================
    // Factory
    // ============================================================

    function test_FactoryCreateAgent() public {
        AgentYieldFactory f = new AgentYieldFactory(poolManager);

        (uint256 id, address hookAddr) = f.createAgent("FactoryAgent", AgentYieldHook.StrategyMode.Aggressive, address(this));

        assertEq(id, 0);
        assertTrue(hookAddr != address(0));
        assertEq(f.getAgentCount(), 1);

        (address hookAddr_, address owner_, string memory name_, AgentYieldHook.StrategyMode mode_, uint256 createdAt_) = f.agents(0);
        assertEq(hookAddr_, hookAddr);
        assertEq(owner_, address(this));
        assertEq(name_, "FactoryAgent");
        assertEq(uint8(mode_), uint8(AgentYieldHook.StrategyMode.Aggressive));
    }

    function test_FactoryMultipleAgents() public {
        AgentYieldFactory f = new AgentYieldFactory(poolManager);

        f.createAgent("Agent1", AgentYieldHook.StrategyMode.Balanced, address(this));
        f.createAgent("Agent2", AgentYieldHook.StrategyMode.Conservative, address(this));
        f.createAgent("Agent3", AgentYieldHook.StrategyMode.Aggressive, address(this));

        assertEq(f.getAgentCount(), 3);

        AgentYieldFactory.AgentInfo[] memory owned = f.getAgentsByOwner(address(this));
        assertEq(owned.length, 3);
    }
}
