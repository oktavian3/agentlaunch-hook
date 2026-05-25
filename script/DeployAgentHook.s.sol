// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {AgentHook} from "../src/AgentHook.sol";

/// @title DeployAgentHook — Deploy an AgentHook for an AI agent
/// @notice Deploys a new AgentHook instance owned by the specified agent wallet
///         on X Layer (chain 196)
contract DeployAgentHook is Script {
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;

    function run() external {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(privateKey);

        // For a real AI agent, get these from env or pass as args
        address agentWallet = vm.envOr("AGENT_WALLET", deployer);
        string memory agentName = vm.envString("AGENT_NAME");
        string memory agentDesc = vm.envString("AGENT_DESC");
        uint24 agentFee = uint24(vm.envOr("AGENT_FEE", uint256(30)));

        vm.startBroadcast(privateKey);

        AgentHook hook = new AgentHook(
            IPoolManager(POOL_MANAGER),
            agentWallet,
            agentName,
            agentDesc,
            agentFee
        );

        vm.stopBroadcast();

        console.log("AgentHook deployed!");
        console.log("  Hook Address:", address(hook));
        console.log("  Agent Wallet:", agentWallet);
        console.log("  Agent Name:", agentName);
        console.log("  Agent Fee:", agentFee);
        console.log("  PoolManager:", POOL_MANAGER);
        console.log("  Chain: X Layer (196)");
    }
}
