// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {AgentYieldHook} from "./AgentYieldHook.sol";

/// @title AgentYieldFactory — Deploy AI Agent Yield Hooks in 1 TX
/// @notice One-click factory: deploy a Hook contract instantly.
///         Pool creation is handled separately by the AI bot (X Layer PoolManager restrictions).
contract AgentYieldFactory {
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
        AgentYieldHook.StrategyMode mode
    );

    constructor(IPoolManager _poolManager) {
        require(address(_poolManager) != address(0), "AYF: zero pool manager");
        poolManager = _poolManager;
    }

    function createAgent(
        string memory _name,
        AgentYieldHook.StrategyMode _mode,
        address _agentWallet
    ) external returns (uint256 agentId, address hookAddress) {
        require(bytes(_name).length > 0, "AYF: name required");
        require(bytes(_name).length <= 32, "AYF: name too long");
        require(uint8(_mode) <= 2, "AYF: invalid mode");
        require(_agentWallet != address(0), "AYF: zero wallet");

        AgentYieldHook hook = new AgentYieldHook(
            poolManager, _agentWallet, _name, _mode
        );
        hookAddress = address(hook);

        agentId = agents.length;
        agents.push(AgentInfo({
            hookAddress: hookAddress,
            owner: _agentWallet,
            name: _name,
            mode: _mode,
            createdAt: block.timestamp
        }));
        ownerAgentCount[_agentWallet]++;

        emit AgentCreated(agentId, hookAddress, _agentWallet, _name, _mode);
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
}
