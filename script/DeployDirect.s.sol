// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {AgentYieldHook} from "../src/AgentYieldHook.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";

/// @title DeployDirect — Deploy Hook + Factory on X Layer
contract DeployDirect is Script {
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        vm.startBroadcast(pk);

        // Deploy a Hook directly
        AgentYieldHook hook = new AgentYieldHook(
            IPoolManager(POOL_MANAGER),
            vm.addr(pk),
            "Agent02",
            AgentYieldHook.StrategyMode.Balanced
        );

        vm.stopBroadcast();

        console.log("=== Hook Deployed ===");
        console.log("Address:", address(hook));
        console.log("Name:", hook.agentName());
        console.log("Wallet:", hook.agentWallet());
        console.log("Alive:", hook.alive() ? "yes" : "no");
        console.log("");
        console.log("Now update dashboard with this address.");
    }
}
