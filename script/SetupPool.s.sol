// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console} from "forge-std/Script.sol";
import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {LPFeeLibrary} from "v4-core/libraries/LPFeeLibrary.sol";
import {AgentYieldFactory} from "../src/AgentYieldFactory.sol";
import {AgentYieldHook} from "../src/AgentYieldHook.sol";
import {IERC20} from "openzeppelin-contracts/contracts/token/ERC20/IERC20.sol";

/// @notice Creates a V4 Pool OKB/USDT0 and seeds liquidity for AgentYield demo
contract SetupPoolAndAgent is Script {
    // PoolManager (Satya's own deploy)
    address constant POOL_MANAGER = 0xDa4436558E501DFE8B0c1A102b927808F52bA446;

    // USDT0 on X Layer
    address constant USDT0 = 0x779Ded0c9e1022225f8E0630b35a9b54bE713736;

    // New Factory
    address constant FACTORY = 0x80bfBc37E3c17C407fd142cE6FB561EC421A7336;

    // LPFeeLibrary
    using LPFeeLibrary for uint24;

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);

        vm.startBroadcast(pk);

        // Create an agent first (so we have a hook)
        AgentYieldFactory factory = AgentYieldFactory(FACTORY);
        factory.createAgent("AutoYieldAgent", AgentYieldHook.StrategyMode.Balanced, deployer);

        console.log("Agent created!");

        vm.stopBroadcast();

        // Get the agent address from factory
        uint256 count = factory.getAgentCount();
        console.log("Agent count:", count);
        (address hookAddr,,, ,) = factory.agents(count - 1);
        console.log("Hook address:", hookAddr);
    }
}
