// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {AgentLaunchHook} from "../src/AgentLaunchHook.sol";

/// @title DeployAgentLaunchHook — Deploys the AgentLaunchHook
/// @notice Deploys the hook contract on X Layer (chain 196)
contract DeployAgentLaunchHook is Script {
    // X Layer PoolManager address
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;

    function run() external {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(privateKey);

        vm.startBroadcast(privateKey);

        AgentLaunchHook hook = new AgentLaunchHook(IPoolManager(POOL_MANAGER));

        vm.stopBroadcast();

        console.log("AgentLaunchHook deployed!");
        console.log("  Address:", address(hook));
        console.log("  Deployer:", deployer);
        console.log("  PoolManager:", POOL_MANAGER);
        console.log("  Chain: X Layer (196)");
    }
}
