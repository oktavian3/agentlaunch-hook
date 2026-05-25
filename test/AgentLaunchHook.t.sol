// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test, console} from "forge-std/Test.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {AgentLaunchHook} from "../src/AgentLaunchHook.sol";

contract AgentLaunchHookTest is Test {
    using PoolIdLibrary for PoolKey;

    AgentLaunchHook public hook;
    address public deployer = address(0x1);
    address public creator = address(0x2);
    address public alice = address(0x3);
    address public bob = address(0x4);

    IPoolManager public poolManager = IPoolManager(address(0x100));
    bytes32 public testPoolId;

    // The AgentMetadata struct: name(0), symbol(1), agentPersonality(2), creator(3),
    // socialTwitter(4), socialDiscord(5), socialWebsite(6), agentFee(7), createdAt(8), exists(9)

    function setUp() public {
        vm.prank(deployer);
        hook = new AgentLaunchHook(poolManager);
        testPoolId = bytes32(uint256(1));
    }

    // ============================================================
    // Deploy
    // ============================================================

    function test_Deploy() public {
        assertEq(address(hook.poolManager()), address(poolManager));
        assertEq(hook.owner(), deployer);
        assertEq(hook.totalAgents(), 0);
    }

    function test_DefaultConstants() public {
        assertEq(hook.DEFAULT_AGENT_FEE(), 30);
        assertEq(hook.MAX_AGENT_FEE(), 200);
        assertEq(hook.MIN_AGENT_FEE(), 5);
        assertEq(hook.DEV_SHARE_BPS(), 2000);
        assertEq(hook.PROTOCOL_SHARE_BPS(), 1000);
        assertEq(hook.LP_SHARE_BPS(), 7000);
    }

    // ============================================================
    // afterInitialize — Agent Registration
    // ============================================================

    function test_AfterInitialize_RegistersAgent() public {
        _registerAgent();

        // Read agents mapping
        AgentLaunchHook.AgentMetadata memory a = hook.getAgent(testPoolId);
        assertTrue(a.exists);
        assertEq(hook.totalAgents(), 1);
    }

    function test_AfterInitialize_RevertsOnDuplicate() public {
        _registerAgent();

        PoolKey memory key = _makePoolKey();
        vm.prank(address(poolManager));
        vm.expectRevert(bytes("ALH: already registered"));
        hook.afterInitialize(address(0), key, 0, 0);
    }

    // ============================================================
    // configureAgent
    // ============================================================

    function test_ConfigureAgent_Success() public {
        _registerAgent();
        _configureAgent();

        AgentLaunchHook.AgentMetadata memory a = hook.getAgent(testPoolId);
        assertEq(a.name, "TestAgent");
        assertEq(a.symbol, "TAG");
        assertEq(a.agentPersonality, "An AI agent for testing");
        assertEq(a.creator, creator);
        assertEq(a.agentFee, 50);
    }

    function test_ConfigureAgent_RevertsIfNotRegistered() public {
        vm.prank(creator);
        vm.expectRevert(bytes("ALH: not registered"));
        hook.configureAgent(testPoolId, "Test", "TST", "test", "", "", "", 30);
    }

    function test_ConfigureAgent_RevertsIfAlreadyConfigured() public {
        _registerAgent();
        _configureAgent();

        vm.prank(address(0x99));
        vm.expectRevert(bytes("ALH: already configured"));
        hook.configureAgent(testPoolId, "Another", "ANR", "another", "", "", "", 30);
    }

    function test_ConfigureAgent_RevertsOnInvalidFee() public {
        _registerAgent();

        vm.prank(creator);
        vm.expectRevert(bytes("ALH: invalid fee"));
        hook.configureAgent(testPoolId, "Test", "TST", "test", "", "", "", 300);
    }

    function test_ConfigureAgent_RevertsOnEmptyName() public {
        _registerAgent();

        vm.prank(creator);
        vm.expectRevert(bytes("ALH: name required"));
        hook.configureAgent(testPoolId, "", "TST", "test", "", "", "", 30);
    }

    // ============================================================
    // updateAgentMetadata
    // ============================================================

    function test_UpdateMetadata() public {
        _registerAgent();
        _configureAgent();

        vm.prank(creator);
        hook.updateAgentMetadata(testPoolId, "Updated AI personality", "https://twitter.com/new", "https://discord.gg/new", "");

        AgentLaunchHook.AgentMetadata memory m = hook.getAgent(testPoolId);
        assertEq(m.socialTwitter, "https://twitter.com/new");
        assertEq(m.socialDiscord, "https://discord.gg/new");
    }

    function test_UpdateMetadata_RevertsIfNotCreator() public {
        _registerAgent();
        _configureAgent();

        vm.prank(alice);
        vm.expectRevert(bytes("ALH: not creator"));
        hook.updateAgentMetadata(testPoolId, "test", "", "", "");
    }

    // ============================================================
    // updateFee
    // ============================================================

    function test_UpdateFee() public {
        _registerAgent();
        _configureAgent();

        vm.prank(creator);
        hook.updateFee(testPoolId, 100);

        AgentLaunchHook.AgentMetadata memory m = hook.getAgent(testPoolId);
        assertEq(m.agentFee, 100);
    }

    function test_UpdateFee_RevertsOnInvalidFee() public {
        _registerAgent();
        _configureAgent();

        vm.prank(creator);
        vm.expectRevert(bytes("ALH: invalid fee"));
        hook.updateFee(testPoolId, 1);
    }

    // ============================================================
    // getAgentPrice
    // ============================================================

    function test_GetAgentPrice_ZeroSupply() public {
        _registerAgent();
        // With supply=0, fillRatio=0, so price = basePrice = 1000000000 (0.000000001 ether)
        assertEq(hook.getAgentPrice(testPoolId), uint256(hook.DEFAULT_BASE_PRICE()));
    }

    function test_GetAgentPrice_AfterConfigure() public {
        _registerAgent();
        // Price should be basePrice since supply is 0
        uint256 price = hook.getAgentPrice(testPoolId);
        // basePrice = DEFAULT_BASE_PRICE = 0.000000001 ether = 1000000000
        assertEq(price, uint256(hook.DEFAULT_BASE_PRICE()));
    }

    // ============================================================
    // getAgentByIndex / getPoolAgents
    // ============================================================

    function test_GetAgentByIndex() public {
        _registerAgent();
        bytes32 pid = hook.getAgentByIndex(0);
        assertEq(pid, testPoolId);
    }

    function test_GetAgentByIndex_RevertsOutOfBounds() public {
        vm.expectRevert(bytes("ALH: index out"));
        hook.getAgentByIndex(0);
    }

    function test_GetPoolAgents() public {
        _registerAgent();

        (bytes32[] memory ids, ) = hook.getPoolAgents(0, 10);
        assertEq(ids.length, 1);
        assertEq(ids[0], testPoolId);
    }

    // ============================================================
    // Ownership
    // ============================================================

    function test_TransferOwnership() public {
        vm.prank(deployer);
        hook.transferOwnership(address(0x5));
        assertEq(hook.owner(), address(0x5));
    }

    function test_TransferOwnership_RevertsFromNonOwner() public {
        vm.prank(alice);
        vm.expectRevert(bytes("ALH: not owner"));
        hook.transferOwnership(address(0x5));
    }

    // ============================================================
    // withdraw functions
    // ============================================================

    function test_WithdrawDev_RevertsIfNoFees() public {
        _registerAgent();
        _configureAgent();

        vm.prank(creator);
        vm.expectRevert(bytes("ALH: no fees"));
        hook.withdrawDevFees(testPoolId);
    }

    function test_WithdrawProtocol_RevertsIfNoFees() public {
        vm.prank(deployer);
        vm.expectRevert(bytes("ALH: no protocol fees"));
        hook.withdrawProtocolFees(testPoolId);
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

    function _registerAgent() internal {
        PoolKey memory key = _makePoolKey();
        testPoolId = PoolId.unwrap(key.toId());

        vm.prank(address(poolManager));
        hook.afterInitialize(address(0), key, 0, 0);
    }

    function _configureAgent() internal {
        vm.prank(creator);
        hook.configureAgent(testPoolId, "TestAgent", "TAG", "An AI agent for testing", "https://twitter.com/testagent", "", "", 50);
    }
}
