// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";

/// @title DeployAgentYield — Deploy AgentYield Factory on X Layer
/// @notice 1-command deployment. After deploy, anyone can create agents from the dashboard.
contract DeployAgentYield is Script {
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;

    function run() external {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(privateKey);

        vm.startBroadcast(privateKey);

        AgentYieldFactory factory = new AgentYieldFactory(
            IPoolManager(POOL_MANAGER)
        );

        vm.stopBroadcast();

        console.log("=== AgentYield Factory Deployed! ===");
        console.log("---");
        console.log("  Factory:", address(factory));
        console.log("  PoolManager:", POOL_MANAGER);
        console.log("  Chain: X Layer (196)");
        console.log("  Deployer:", deployer);
        console.log("---");
        console.log("");
        console.log("  Set FACTORY_ADDRESS in your .env:");
        console.log("  FACTORY_ADDRESS=", address(factory));
        console.log("");
        console.log("  Anyone can now create agents via the dashboard!");
    }
}
