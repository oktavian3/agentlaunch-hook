// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {PoolManager} from "v4-core/src/PoolManager.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";

/// @title CreatePool — Create a V4 pool on OUR PoolManager
/// @notice After deploying our own PoolManager, use this to create a pool
///         linked to our Hook.
///         Run AFTER DeployPool.s.sol has been executed.
///         Set NEW_POOL_MANAGER and HOOK_ADDRESS in .env first.
contract CreatePool is Script {
    using PoolIdLibrary for PoolKey;

    address constant WOKB = 0x4200000000000000000000000000000000000006;
    address constant USDC = 0x74b7f16337b8972027f6196a17a631ac6de26d22;

    // These will be read from env
    // NEW_POOL_MANAGER=0x...
    // NEW_HOOK=0x...

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address pmAddr = vm.envAddress("NEW_POOL_MANAGER");
        address hookAddr = vm.envAddress("NEW_HOOK");

        vm.startBroadcast(pk);

        PoolManager pm = PoolManager(pmAddr);

        // Build PoolKey: WOKB / USDC with dynamic fee + tickSpacing 60 + our Hook
        PoolKey memory key = PoolKey({
            currency0: Currency.wrap(WOKB),
            currency1: Currency.wrap(USDC),
            fee: 0,       // 0 = dynamic fee (enables fee override in beforeSwap)
            tickSpacing: 60,
            hooks: IHooks(hookAddr)
        });

        // sqrtPriceX96 = 79228162514264337593543950336 (price 1.0)
        // This initializes the pool at WOKB=USDC price
        int24 tick = pm.initialize(key, 79228162514264337593543950336);

        vm.stopBroadcast();

        bytes32 poolId = PoolId.unwrap(key.toId());
        console.log("=== Pool Created! ===");
        console.log("  PoolManager:", pmAddr);
        console.log("  Hook:", hookAddr);
        console.log("  Pair: WOKB / USDC");
        console.log("  Fee: dynamic (0)");
        console.log("  Tick Spacing: 60");
        console.log("  Initial Tick:", tick);
        console.log("  Pool ID:");
        console.logBytes32(poolId);
        console.log("");
        console.log("  Pool created at PoolManager. Anyone can now swap or add liquidity.");
    }
}
