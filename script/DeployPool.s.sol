// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {PoolManager} from "v4-core/PoolManager.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {Hooks} from "v4-core/libraries/Hooks.sol";
import {AgentYieldHook} from "../src/AgentYieldHook.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";

/// @title DeployPool — Deploy our own PoolManager + create V4 pool + Hook
/// @notice Because X Layer's built-in PoolManager (0x360E68...) doesn't have initialize(),
///         we deploy our own PoolManager so we can create pools + link Hooks.
contract DeployPool is Script {
    // Real tokens on X Layer
    address constant WOKB = 0x4200000000000000000000000000000000000006;
    address constant USDC = 0x74b7F16337b8972027F6196A17a631aC6dE26d22;

    // X Layer's existing PoolManager (for reference — but we'll deploy our own)
    // address constant OLD_POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);

        vm.startBroadcast(pk);

        // 1. Deploy OUR OWN PoolManager (so we can create pools)
        PoolManager poolManager = new PoolManager(deployer);
        console.log("=== PoolManager Deployed ===");
        console.log("  Address:", address(poolManager));
        console.log("  Owner:", deployer);

        // 2. Deploy Factory (using NEW PoolManager)
        AgentYieldFactory factory = new AgentYieldFactory(
            IPoolManager(address(poolManager))
        );
        console.log("  Factory:", address(factory));

        // 3. Deploy a Hook directly so we have a pool + hook combo
        AgentYieldHook hook = new AgentYieldHook(
            IPoolManager(address(poolManager)),
            deployer,
            "MyYieldAgent",
            AgentYieldHook.StrategyMode.Balanced
        );
        console.log("  Hook:", address(hook));

        // 4. Create a pool via PoolManager.initialize()
        // PoolKey(currency0, currency1, fee, tickSpacing, hooks)
        // NOTE: WOKB is address(0x4200...), USDC is address(0x74b7...)
        // For a V4 pool to work with our Hook, we need the Hook address to have the right flags
        // BEFORE_SWAP_FLAG | AFTER_SWAP_FLAG | BEFORE_INITIALIZE_FLAG | AFTER_INITIALIZE_FLAG
        // = 0x80 | 0x100 | 0x1 | 0x2 = 0x183
        // But the hook address LOW bits encode these flags
        // Since contract addresses are deterministic via CREATE, we need to check Hook address bits
        // If Hook address doesn't have the flags, we'll skip pool init for now
        // and create pool from Factory during createAgent() instead
        
        console.log("");
        console.log("=== IMPORTANT ===");
        console.log("  Hook address must have flag bits set for pool creation.");
        console.log("  Creating pool requires: deployer calls poolManager.initialize()");
        console.log("  with PoolKey that has hooks=address(hook).");
        console.log("");
        console.log("  To create pool from CLI:");
        console.log("  forge script script/CreatePool.s.sol --rpc-url xlayer --broadcast");
        console.log("");

        vm.stopBroadcast();

        console.log("---");
        console.log("  NEXT STEPS:");
        console.log("  1. Set FACTORY_ADDRESS in .env to:", address(factory));
        console.log("  2. Set NEW_POOL_MANAGER in .env to:", address(poolManager));
        console.log("  3. Update dashboard FACTORY_ADDRESS constant");
        console.log("  4. Create pool via separate script or Factory");
    }
}
