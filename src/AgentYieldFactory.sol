// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {Hooks} from "v4-core/libraries/Hooks.sol";
import {LPFeeLibrary} from "v4-core/libraries/LPFeeLibrary.sol";
import {AgentYieldHook} from "./AgentYieldHook.sol";

/// @title AgentYieldFactory — Deploy AI Agent Yield Hooks in 1 TX
/// @notice One-click factory: deploy Hook + create pool in 1 transaction.
contract AgentYieldFactory {
    using LPFeeLibrary for uint24;

    struct AgentInfo {
        address hookAddress;
        address owner;
        string name;
        AgentYieldHook.StrategyMode mode;
        uint256 createdAt;
    }

    IPoolManager public immutable poolManager;
    AgentInfo[] public agents;
    mapping(address => uint256) public ownerAgentCount;

    event AgentCreated(
        uint256 indexed agentId,
        address indexed hookAddress,
        address indexed owner,
        string name,
        address token0,
        address token1,
        uint24 fee,
        int24 tickSpacing,
        AgentYieldHook.StrategyMode mode
    );

    constructor(IPoolManager _poolManager) {
        require(address(_poolManager) != address(0), "AYF: zero pool manager");
        poolManager = _poolManager;
    }

    function createAgent(
        string memory _name,
        address _token0,
        address _token1,
        AgentYieldHook.StrategyMode _mode
    ) external returns (uint256 agentId, address hookAddress) {
        require(bytes(_name).length > 0, "AYF: name required");
        require(_token0 != address(0) && _token1 != address(0), "AYF: zero token");
        require(_token0 != _token1, "AYF: same token");
        require(uint8(_mode) <= 2, "AYF: invalid mode");

        (address currency0, address currency1) = _token0 < _token1
            ? (_token0, _token1) : (_token1, _token0);

        AgentYieldHook.StrategyConfig memory config = _getStrategyConfig(_mode);

        AgentYieldHook hook = new AgentYieldHook(
            poolManager, msg.sender, _name, _mode
        );
        hookAddress = address(hook);

        PoolKey memory key = PoolKey({
            currency0: Currency.wrap(currency0),
            currency1: Currency.wrap(currency1),
            fee: config.fee,
            tickSpacing: _getTickSpacing(config.fee),
            hooks: IHooks(hookAddress)
        });

        uint160 sqrtPriceX96 = 79228162514264337593543950336;
        poolManager.initialize(key, sqrtPriceX96);
        hook.initialize(key);

        agentId = agents.length;
        agents.push(AgentInfo({
            hookAddress: hookAddress,
            owner: msg.sender,
            name: _name,
            mode: _mode,
            createdAt: block.timestamp
        }));
        ownerAgentCount[msg.sender]++;

        emit AgentCreated(
            agentId, hookAddress, msg.sender, _name,
            currency0, currency1, config.fee,
            _getTickSpacing(config.fee), _mode
        );
    }

    function getAgents() external view returns (AgentInfo[] memory) {
        return agents;
    }

    function getAgentCount() external view returns (uint256) {
        return agents.length;
    }

    function getAgentsByOwner(address _owner) external view returns (AgentInfo[] memory) {
        uint256 count = ownerAgentCount[_owner];
        AgentInfo[] memory result = new AgentInfo[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < agents.length; i++) {
            if (agents[i].owner == _owner) {
                result[idx] = agents[i];
                idx++;
            }
        }
        return result;
    }

    function _getStrategyConfig(AgentYieldHook.StrategyMode mode)
        internal pure returns (AgentYieldHook.StrategyConfig memory)
    {
        if (mode == AgentYieldHook.StrategyMode.Aggressive) {
            return AgentYieldHook.StrategyConfig(mode, 1, 100, "Aggressive");
        } else if (mode == AgentYieldHook.StrategyMode.Balanced) {
            return AgentYieldHook.StrategyConfig(mode, 30, 600, "Balanced");
        } else {
            return AgentYieldHook.StrategyConfig(mode, 100, 2000, "Conservative");
        }
    }

    function _getTickSpacing(uint24 fee) internal pure returns (int24) {
        if (fee <= 10) return 2;
        if (fee <= 50) return 10;
        if (fee <= 200) return 60;
        return 200;
    }
}
