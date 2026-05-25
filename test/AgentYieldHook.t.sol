// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test, console} from "forge-std/Test.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {BalanceDelta} from "v4-core/types/BalanceDelta.sol";
import {AgentYieldHook} from "../src/AgentYieldHook.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";

contract AgentYieldHookTest is Test {
    using PoolIdLibrary for PoolKey;

    AgentYieldHook public hook;
    AgentYieldFactory public factory;

    address public agentWallet = address(0x42);
    address public user1 = address(0x101);
    address public user2 = address(0x102);
    address public deployer = address(0x1);
    IPoolManager public poolManager = IPoolManager(address(0x100));
    address public token0 = address(0x100001);
    address public token1 = address(0x100002);

    PoolKey public testPoolKey;

    function setUp() public {
        // Deploy Hook directly (factory needs real PoolManager for pool creation)
        vm.prank(deployer);
        hook = new AgentYieldHook(
            poolManager,
            agentWallet,
            "TestYieldAgent",
            AgentYieldHook.StrategyMode.Balanced
        );

        // Build pool key for initialization
        testPoolKey = PoolKey({
            currency0: Currency.wrap(token0),
            currency1: Currency.wrap(token1),
            fee: 30,
            tickSpacing: 60,
            hooks: hook
        });
        
        // Initialize as the factory deployer
        vm.prank(hook.factory());
        hook.initialize(testPoolKey);
    }

    // ============================================================
    // Deploy & Factory
    // ============================================================

    function test_Deploy() public {
        assertEq(hook.agentName(), "TestYieldAgent");
        assertEq(hook.agentWallet(), agentWallet);
        assertTrue(hook.initialized());
        assertEq(address(hook.poolManager()), address(poolManager));
    }

    function test_InitialPoolKey() public {
        (Currency c0, Currency c1,,,) = hook.poolKey();
        assertEq(Currency.unwrap(c0), token0);
        assertEq(Currency.unwrap(c1), token1);
    }

    // ============================================================
    // Strategy
    // ============================================================

    function test_DefaultStrategy_Balanced() public {
        (AgentYieldHook.StrategyMode mode, uint24 fee, int24 tickRange,) = hook.strategy();
        assertEq(uint8(mode), uint8(AgentYieldHook.StrategyMode.Balanced));
        assertEq(fee, 30);
        assertEq(tickRange, 600);
    }

    // ============================================================
    // Deposit
    // ============================================================

    function test_Deposit() public {
        vm.prank(user1);
        hook.deposit(100 ether);

        (uint256 amount,) = hook.getDepositorInfo(user1);
        // 100 - 0.1% deposit fee = 99.9
        assertEq(amount, 99.9 ether);
        assertEq(hook.totalDeposits(), 99.9 ether);
    }

    function test_DepositTwoUsers() public {
        vm.prank(user1);
        hook.deposit(100 ether);

        vm.prank(user2);
        hook.deposit(50 ether);

        assertEq(hook.getDepositorCount(), 2);
        // (100 + 50) - 0.1% = 149.85
        assertEq(hook.totalDeposits(), 149.85 ether);
        assertEq(hook.treasuryBalance(), 0.15 ether); // 0.1% of 150
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
        vm.prank(user1);
        hook.deposit(100 ether);

        vm.prank(user1);
        hook.withdraw(0); // withdraw all

        (uint256 remaining,) = hook.getDepositorInfo(user1);
        assertEq(remaining, 0);
    }

    function test_Withdraw_RevertsOnNoDeposit() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: no deposit"));
        hook.withdraw(0);
    }

    function test_Withdraw_RevertsOnExcess() public {
        vm.prank(user1);
        hook.deposit(100 ether);

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
        (AgentYieldHook.StrategyMode mode, uint24 fee,,) = hook.strategy();
        assertEq(fee, 50);
    }

    function test_SetFee_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.setFee(50);
    }

    function test_SetMode() public {
        vm.prank(agentWallet);
        hook.setMode(AgentYieldHook.StrategyMode.Aggressive);
        (AgentYieldHook.StrategyMode mode,,,) = hook.strategy();
        assertEq(uint8(mode), uint8(AgentYieldHook.StrategyMode.Aggressive));
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

    // ============================================================
    // Treasury & Reinvest
    // ============================================================

    function test_DepositAndTreasury() public {
        vm.prank(user1);
        hook.deposit(1000 ether);

        assertTrue(hook.treasuryBalance() > 0);
    }

    function test_Reinvest() public {
        vm.prank(user1);
        hook.deposit(1000 ether);

        uint256 treasury = hook.treasuryBalance();
        assertTrue(treasury > 0);

        // Warp past cooldown
        vm.warp(block.timestamp + hook.REINVEST_COOLDOWN() + 1);

        vm.prank(agentWallet);
        hook.reinvest();

        assertEq(hook.treasuryBalance(), 0);
    }

    function test_Reinvest_RevertsFromNonAgent() public {
        vm.prank(user1);
        vm.expectRevert(bytes("AY: not agent"));
        hook.reinvest();
    }

    function test_Reinvest_RevertsOnEmpty() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AY: empty treasury"));
        hook.reinvest();
    }

    // ============================================================
    // View Functions
    // ============================================================

    function test_GetAgentInfo() public {
        (string memory name, address wallet, uint256 tvl, uint256 treasury,, uint256 depCount, uint256 msgCount, AgentYieldHook.StrategyMode mode, uint24 fee, uint128 liq, bool alive) = hook.getAgentInfo();

        assertEq(name, "TestYieldAgent");
        assertEq(wallet, agentWallet);
        assertEq(tvl, 0);
        assertEq(treasury, 0);
        assertEq(depCount, 0);
        assertEq(msgCount, 0);
        assertEq(fee, 30);
        assertTrue(alive);
    }

    function test_GetMessages() public {
        vm.prank(agentWallet);
        hook.postMessage("msg1");
        vm.prank(agentWallet);
        hook.postMessage("msg2");

        string[] memory msgs = hook.getAllMessages();
        assertEq(msgs.length, 2);
        assertEq(msgs[0], "msg1");
        assertEq(msgs[1], "msg2");
    }

    // ============================================================
    // Hook Callbacks (via PoolManager)
    // ============================================================

    function test_BeforeSwap_ReturnsSelector() public {
        PoolKey memory key = _makePoolKey();
        vm.prank(address(poolManager));
        bytes4 selector = hook.beforeInitialize(address(0), key, 0);
        assertEq(selector, hook.beforeInitialize.selector);
    }

    function test_AfterSwap_Accumulates() public {
        // Need initialized pool to accumulate
        vm.prank(address(poolManager));
        hook.afterInitialize(address(0), testPoolKey, 0, 0);
    }

    // ============================================================
    // Helpers
    // ============================================================

    function _makePoolKey() internal view returns (PoolKey memory) {
        return PoolKey({
            currency0: Currency.wrap(token0),
            currency1: Currency.wrap(token1),
            fee: 30,
            tickSpacing: 60,
            hooks: hook
        });
    }
}
