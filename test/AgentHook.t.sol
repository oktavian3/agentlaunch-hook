// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test, console} from "forge-std/Test.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {BalanceDelta} from "v4-core/types/BalanceDelta.sol";
import {AgentHook} from "../src/AgentHook.sol";

contract AgentHookTest is Test {
    using PoolIdLibrary for PoolKey;

    AgentHook public hook;
    address public agentWallet = address(0x42);
    address public deployer = address(0x1);
    address public swapper = address(0x99);
    IPoolManager public poolManager = IPoolManager(address(0x100));
    bytes32 public testPoolId;

    function setUp() public {
        vm.prank(deployer);
        hook = new AgentHook(
            poolManager,
            agentWallet,
            "SoulAgent",
            "An autonomous AI agent that manages its own DeFi pool",
            30
        );
        testPoolId = bytes32(uint256(1));
    }

    // ============================================================
    // Deploy
    // ============================================================

    function test_Deploy() public {
        assertEq(address(hook.poolManager()), address(poolManager));

        AgentHook.AgentConfig memory c = hook.getAgentInfoStruct();
        assertEq(c.agentWallet, agentWallet);
        assertEq(c.agentName, "SoulAgent");
        assertEq(c.agentDescription, "An autonomous AI agent that manages its own DeFi pool");
        assertEq(c.agentFee, 30);
        assertTrue(c.createdAt > 0);
        assertTrue(c.lastHeartbeat > 0);
        assertTrue(c.exists);
    }

    function test_Deploy_RevertsOnZeroWallet() public {
        vm.expectRevert(bytes("AgentHook: zero wallet"));
        new AgentHook(poolManager, address(0), "Test", "desc", 30);
    }

    function test_Deploy_RevertsOnEmptyName() public {
        vm.expectRevert(bytes("AgentHook: name required"));
        new AgentHook(poolManager, agentWallet, "", "desc", 30);
    }

    function test_Deploy_RevertsOnInvalidFeeLow() public {
        vm.expectRevert(bytes("AgentHook: invalid fee"));
        new AgentHook(poolManager, agentWallet, "Test", "desc", 0);
    }

    function test_Deploy_RevertsOnInvalidFeeHigh() public {
        vm.expectRevert(bytes("AgentHook: invalid fee"));
        new AgentHook(poolManager, agentWallet, "Test", "desc", 1001);
    }

    function test_DefaultConstants() public {
        assertEq(hook.MAX_AGENT_FEE(), 1000);
        assertEq(hook.MIN_AGENT_FEE(), 1);
        assertEq(hook.DEFAULT_AGENT_FEE(), 30);
    }

    // ============================================================
    // Agent Identity & Fee Control
    // ============================================================

    function test_SetFee() public {
        vm.prank(agentWallet);
        hook.setFee(50);

        AgentHook.AgentConfig memory c = hook.getAgentInfoStruct();
        assertEq(c.agentFee, 50);
    }

    function test_SetFee_RevertsFromNonAgent() public {
        vm.prank(swapper);
        vm.expectRevert(bytes("AgentHook: not agent"));
        hook.setFee(50);
    }

    function test_SetFee_RevertsOnInvalidFee() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AgentHook: invalid fee"));
        hook.setFee(1001);
    }

    // ============================================================
    // Heartbeat
    // ============================================================

    function test_Heartbeat() public {
        vm.warp(block.timestamp + 1000);
        vm.prank(agentWallet);
        hook.heartbeat();

        AgentHook.AgentConfig memory c = hook.getAgentInfoStruct();
        assertEq(c.lastHeartbeat, block.timestamp);
    }

    function test_Heartbeat_RevertsFromNonAgent() public {
        vm.prank(swapper);
        vm.expectRevert(bytes("AgentHook: not agent"));
        hook.heartbeat();
    }

    // ============================================================
    // Post Message
    // ============================================================

    function test_PostMessage() public {
        vm.prank(agentWallet);
        hook.postMessage("Hello from the AI agent!");

        assertEq(hook.getMessageCount(), 1);
        AgentHook.AgentMessage memory m = hook.getMessageStruct(0);
        assertEq(m.agentWallet, agentWallet);
        assertEq(m.content, "Hello from the AI agent!");
        assertTrue(m.timestamp > 0);
    }

    function test_PostMessage_RevertsFromNonAgent() public {
        vm.prank(swapper);
        vm.expectRevert(bytes("AgentHook: not agent"));
        hook.postMessage("test");
    }

    function test_PostMessage_RevertsOnEmpty() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AgentHook: empty message"));
        hook.postMessage("");
    }

    // ============================================================
    // Description
    // ============================================================

    function test_SetDescription() public {
        vm.prank(agentWallet);
        hook.setDescription("Updated agent description");

        AgentHook.AgentConfig memory c = hook.getAgentInfoStruct();
        assertEq(c.agentDescription, "Updated agent description");
    }

    // ============================================================
    // Ownership Transfer
    // ============================================================

    function test_TransferOwnership() public {
        address newWallet = address(0xCAFE);
        vm.prank(agentWallet);
        hook.transferAgentOwnership(newWallet);

        AgentHook.AgentConfig memory c = hook.getAgentInfoStruct();
        assertEq(c.agentWallet, newWallet);
    }

    function test_TransferOwnership_RevertsFromNonAgent() public {
        vm.prank(swapper);
        vm.expectRevert(bytes("AgentHook: not agent"));
        hook.transferAgentOwnership(address(0xCAFE));
    }

    // ============================================================
    // afterInitialize
    // ============================================================

    function test_AfterInitialize() public {
        PoolKey memory key = _makePoolKey();
        testPoolId = PoolId.unwrap(key.toId());

        vm.prank(address(poolManager));
        hook.afterInitialize(address(0), key, 0, 0);

        assertTrue(hook.initialized());
        assertEq(hook.poolId(), testPoolId);
    }

    function test_AfterInitialize_RevertsOnDuplicate() public {
        PoolKey memory key = _makePoolKey();
        vm.prank(address(poolManager));
        hook.afterInitialize(address(0), key, 0, 0);

        PoolKey memory key2 = _makePoolKey();
        vm.prank(address(poolManager));
        vm.expectRevert(bytes("AgentHook: already initialized"));
        hook.afterInitialize(address(0), key2, 0, 0);
    }

    // ============================================================
    // Withdraw
    // ============================================================

    function test_Withdraw_RevertsIfNoFees() public {
        vm.prank(agentWallet);
        vm.expectRevert(bytes("AgentHook: empty treasury"));
        hook.withdraw();
    }

    function test_Withdraw_RevertsFromNonAgent() public {
        vm.prank(swapper);
        vm.expectRevert(bytes("AgentHook: not agent"));
        hook.withdraw();
    }

    // ============================================================
    // getAgentInfo
    // ============================================================

    function test_GetAgentInfo_AfterDeploy() public {
        (address w, string memory name, string memory desc, uint24 fee, uint40 created, uint40 lastSeen, uint256 treasury, uint256 totalFees, uint256 msgCount, bytes32 pid, bool alive) = hook.getAgentInfo();

        assertEq(w, agentWallet);
        assertEq(name, "SoulAgent");
        assertEq(desc, "An autonomous AI agent that manages its own DeFi pool");
        assertEq(fee, 30);
        assertTrue(created > 0);
        assertTrue(lastSeen > 0);
        assertEq(treasury, 0);
        assertEq(totalFees, 0);
        assertEq(msgCount, 0);
        assertEq(pid, bytes32(0));
        assertTrue(alive);
    }

    // ============================================================
    // Helpers
    // ============================================================

    function _makePoolKey() internal view returns (PoolKey memory) {
        return PoolKey({
            currency0: Currency.wrap(address(0)),
            currency1: Currency.wrap(address(0)),
            fee: 0,
            tickSpacing: 60,
            hooks: hook
        });
    }
}
