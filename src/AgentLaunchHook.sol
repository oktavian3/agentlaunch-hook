// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";
import {BalanceDelta} from "v4-core/types/BalanceDelta.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "v4-core/types/BeforeSwapDelta.sol";
import {IHooks} from "v4-core/interfaces/IHooks.sol";
import {Hooks} from "v4-core/libraries/Hooks.sol";
import {LPFeeLibrary} from "v4-core/libraries/LPFeeLibrary.sol";
import {StateLibrary} from "v4-core/libraries/StateLibrary.sol";

/// @title AgentLaunchHook — AI Agent Token Launchpad on Uniswap V4
/// @notice A Uniswap V4 Hook that enables anyone to launch an AI agent token
///         with a built-in bonding curve, dev fee split, and metadata registry.
///         Each agent is tied to a unique pool via its Hook address.
///
/// How it works:
/// 1. Deploy AgentLaunchHook (one instance per agent token)
/// 2. Initialize a Uniswap V4 pool with this Hook address + dynamic fee flag
/// 3. afterInitialize registers the agent in the global registry
/// 4. beforeSwap applies the agent-specific fee logic
/// 5. afterAddLiquidity + afterRemoveLiquidity track bonding curve state
///
/// Fee split on swaps:
/// - 70% LP fee (standard Uniswap fee)
/// - 20% Agent dev share (collected for the agent creator)
/// - 10% Protocol treasury (global fee pool)
///
/// Agent metadata stored on-chain:
///   - name, symbol (token metadata)
///   - agentPersonality (description of AI agent behavior)
///   - creator (deployer address)
///   - socialLinks (Twitter, Discord, etc.)
///   - feeTier (customizable agent fee, default 30 = 0.30%)
contract AgentLaunchHook is IHooks {
    using PoolIdLibrary for PoolKey;
    using LPFeeLibrary for uint24;
    using StateLibrary for IPoolManager;

    // ============================================================
    // Types
    // ============================================================

    struct AgentMetadata {
        string name;
        string symbol;
        string agentPersonality;
        address creator;
        string socialTwitter;
        string socialDiscord;
        string socialWebsite;
        uint24 agentFee;
        uint40 createdAt;
        bool exists;
    }

    struct BondingCurve {
        uint128 maxSupply;
        uint128 currentSupply;
        uint128 basePrice;
        uint128 priceRange;
    }

    struct TreasuryAction {
        uint256 amount;
        uint256 devShare;
        uint256 protocolShare;
        uint256 timestamp;
    }

    // ============================================================
    // State
    // ============================================================

    IPoolManager public immutable poolManager;

    mapping(bytes32 => AgentMetadata) public agents;
    mapping(bytes32 => BondingCurve) public bondingCurves;
    mapping(bytes32 => uint256) public devBalances;
    mapping(bytes32 => uint256) public protocolBalances;
    mapping(bytes32 => TreasuryAction[]) public treasuryHistory;
    mapping(bytes32 => uint256) public totalFeesCollected;

    bytes32[] public allAgentPools;
    address public owner;

    // ============================================================
    // Constants
    // ============================================================

    uint24 public constant DEFAULT_AGENT_FEE = 30;
    uint24 public constant MAX_AGENT_FEE = 200;
    uint24 public constant MIN_AGENT_FEE = 5;
    uint24 public constant FEE_DENOMINATOR = 10000;
    uint256 public constant DEV_SHARE_BPS = 2000;
    uint256 public constant PROTOCOL_SHARE_BPS = 1000;
    uint256 public constant LP_SHARE_BPS = 7000;
    uint128 public constant DEFAULT_MAX_SUPPLY = 1_000_000_000 ether;
    uint128 public constant DEFAULT_BASE_PRICE = 0.000000001 ether;
    uint128 public constant DEFAULT_PRICE_RANGE = 0.001 ether;

    // ============================================================
    // Events
    // ============================================================

    event AgentLaunched(
        bytes32 indexed poolId,
        address indexed creator,
        string name,
        string symbol,
        string agentPersonality,
        uint24 agentFee
    );
    event FeeDistributed(
        bytes32 indexed poolId,
        uint256 totalFee,
        uint256 devShare,
        uint256 protocolShare,
        uint256 lpShare
    );
    event DevWithdrawn(bytes32 indexed poolId, address indexed creator, uint256 amount);
    event ProtocolWithdrawn(bytes32 indexed poolId, address indexed owner, uint256 amount);
    event BondingCurveUpdated(bytes32 indexed poolId, uint128 currentSupply, uint128 price);
    event AgentMetadataUpdated(
        bytes32 indexed poolId,
        string agentPersonality,
        string socialTwitter,
        string socialDiscord,
        string socialWebsite
    );

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyPoolManager() {
        require(msg.sender == address(poolManager), "ALH: not pool manager");
        _;
    }

    modifier onlyAgentCreator(bytes32 poolId) {
        require(agents[poolId].creator == msg.sender, "ALH: not creator");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "ALH: not owner");
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
        owner = msg.sender;
    }

    // ============================================================
    // Hook Implementations
    // ============================================================

    function beforeInitialize(address, PoolKey calldata, uint160)
        external override onlyPoolManager returns (bytes4)
    {
        return IHooks.beforeInitialize.selector;
    }

    function afterInitialize(address, PoolKey calldata key, uint160, int24)
        external override onlyPoolManager returns (bytes4)
    {
        bytes32 poolId = PoolId.unwrap(key.toId());
        require(!agents[poolId].exists, "ALH: already registered");

        agents[poolId] = AgentMetadata({
            name: "",
            symbol: "",
            agentPersonality: "",
            creator: address(0),
            socialTwitter: "",
            socialDiscord: "",
            socialWebsite: "",
            agentFee: DEFAULT_AGENT_FEE,
            createdAt: uint40(block.timestamp),
            exists: true
        });

        bondingCurves[poolId] = BondingCurve({
            maxSupply: DEFAULT_MAX_SUPPLY,
            currentSupply: 0,
            basePrice: DEFAULT_BASE_PRICE,
            priceRange: DEFAULT_PRICE_RANGE
        });

        allAgentPools.push(poolId);
        return IHooks.afterInitialize.selector;
    }

    function beforeAddLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.beforeAddLiquidity.selector;
    }

    function afterAddLiquidity(
        address, PoolKey calldata key, IPoolManager.ModifyLiquidityParams calldata params,
        BalanceDelta, BalanceDelta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BalanceDelta) {
        bytes32 poolId = PoolId.unwrap(key.toId());
        if (agents[poolId].exists && params.liquidityDelta > 0) {
            BondingCurve storage curve = bondingCurves[poolId];
            uint128 supplyIncrease = uint128(uint256(int256(params.liquidityDelta)));
            if (curve.currentSupply + supplyIncrease <= curve.maxSupply) {
                curve.currentSupply += supplyIncrease;
            } else {
                curve.currentSupply = curve.maxSupply;
            }
            _emitBondingEvent(poolId, curve);
        }
        return (IHooks.afterAddLiquidity.selector, BalanceDelta.wrap(0));
    }

    function beforeRemoveLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.beforeRemoveLiquidity.selector;
    }

    function afterRemoveLiquidity(
        address, PoolKey calldata key, IPoolManager.ModifyLiquidityParams calldata params,
        BalanceDelta, BalanceDelta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BalanceDelta) {
        bytes32 poolId = PoolId.unwrap(key.toId());
        if (agents[poolId].exists && params.liquidityDelta < 0) {
            BondingCurve storage curve = bondingCurves[poolId];
            uint128 supplyDecrease = uint128(uint256(int256(-params.liquidityDelta)));
            if (supplyDecrease <= curve.currentSupply) {
                curve.currentSupply -= supplyDecrease;
            } else {
                curve.currentSupply = 0;
            }
            _emitBondingEvent(poolId, curve);
        }
        return (IHooks.afterRemoveLiquidity.selector, BalanceDelta.wrap(0));
    }

    function beforeSwap(
        address, PoolKey calldata key, IPoolManager.SwapParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BeforeSwapDelta, uint24) {
        if (key.fee.isDynamicFee()) {
            bytes32 poolId = PoolId.unwrap(key.toId());
            if (agents[poolId].exists) {
                AgentMetadata memory agent = agents[poolId];
                uint24 totalFee = agent.agentFee;
                BondingCurve memory curve = bondingCurves[poolId];
                if (curve.currentSupply > 0 && curve.maxSupply > 0) {
                    uint256 fillRatio = (uint256(curve.currentSupply) * 1e18) / curve.maxSupply;
                    if (fillRatio < 0.1e18) {
                        totalFee = totalFee + 10;
                    } else if (fillRatio > 0.9e18) {
                        totalFee = totalFee > 10 ? totalFee - 5 : totalFee;
                    }
                }
                if (totalFee > MAX_AGENT_FEE) totalFee = MAX_AGENT_FEE;
                if (totalFee < MIN_AGENT_FEE) totalFee = MIN_AGENT_FEE;
                poolManager.updateDynamicLPFee(key, totalFee);
            }
        }
        return (IHooks.beforeSwap.selector, BeforeSwapDelta.wrap(0), 0);
    }

    function afterSwap(
        address, PoolKey calldata key, IPoolManager.SwapParams calldata, BalanceDelta delta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, int128) {
        bytes32 poolId = PoolId.unwrap(key.toId());
        if (agents[poolId].exists) {
            _distributeFees(poolId, delta);
        }
        return (IHooks.afterSwap.selector, 0);
    }

    function beforeDonate(
        address, PoolKey calldata, uint256, uint256, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.beforeDonate.selector;
    }

    function afterDonate(
        address, PoolKey calldata, uint256, uint256, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.afterDonate.selector;
    }

    // ============================================================
    // Agent Configuration
    // ============================================================

    function configureAgent(
        bytes32 poolId,
        string calldata _name,
        string calldata _symbol,
        string calldata _agentPersonality,
        string calldata _socialTwitter,
        string calldata _socialDiscord,
        string calldata _socialWebsite,
        uint24 _agentFee
    ) external {
        require(agents[poolId].exists, "ALH: not registered");
        require(agents[poolId].creator == address(0), "ALH: already configured");
        require(bytes(_name).length > 0, "ALH: name required");
        require(bytes(_symbol).length > 0, "ALH: symbol required");
        require(bytes(_agentPersonality).length > 0, "ALH: personality required");
        require(_agentFee >= MIN_AGENT_FEE && _agentFee <= MAX_AGENT_FEE, "ALH: invalid fee");

        AgentMetadata storage agent = agents[poolId];
        agent.name = _name;
        agent.symbol = _symbol;
        agent.agentPersonality = _agentPersonality;
        agent.creator = msg.sender;
        agent.socialTwitter = _socialTwitter;
        agent.socialDiscord = _socialDiscord;
        agent.socialWebsite = _socialWebsite;
        agent.agentFee = _agentFee;

        emit AgentLaunched(poolId, msg.sender, _name, _symbol, _agentPersonality, _agentFee);
    }

    function updateAgentMetadata(
        bytes32 poolId,
        string calldata _agentPersonality,
        string calldata _socialTwitter,
        string calldata _socialDiscord,
        string calldata _socialWebsite
    ) external onlyAgentCreator(poolId) {
        AgentMetadata storage agent = agents[poolId];
        if (bytes(_agentPersonality).length > 0) agent.agentPersonality = _agentPersonality;
        if (bytes(_socialTwitter).length > 0) agent.socialTwitter = _socialTwitter;
        if (bytes(_socialDiscord).length > 0) agent.socialDiscord = _socialDiscord;
        if (bytes(_socialWebsite).length > 0) agent.socialWebsite = _socialWebsite;
        emit AgentMetadataUpdated(poolId, agent.agentPersonality, agent.socialTwitter, agent.socialDiscord, agent.socialWebsite);
    }

    function updateFee(bytes32 poolId, uint24 _newFee) external onlyAgentCreator(poolId) {
        require(_newFee >= MIN_AGENT_FEE && _newFee <= MAX_AGENT_FEE, "ALH: invalid fee");
        agents[poolId].agentFee = _newFee;
    }

    // ============================================================
    // Treasury & Withdrawals
    // ============================================================

    function withdrawDevFees(bytes32 poolId) external onlyAgentCreator(poolId) {
        uint256 amount = devBalances[poolId];
        require(amount > 0, "ALH: no fees");
        devBalances[poolId] = 0;
        emit DevWithdrawn(poolId, msg.sender, amount);
    }

    function withdrawProtocolFees(bytes32 poolId) external onlyOwner {
        uint256 amount = protocolBalances[poolId];
        require(amount > 0, "ALH: no protocol fees");
        protocolBalances[poolId] = 0;
        emit ProtocolWithdrawn(poolId, msg.sender, amount);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "ALH: zero address");
        owner = newOwner;
    }

    function devFeeBalanceOf(bytes32 poolId, address creator) external view returns (uint256) {
        if (agents[poolId].creator == creator) return devBalances[poolId];
        return 0;
    }

    function totalAgents() external view returns (uint256) {
        return allAgentPools.length;
    }

    // ============================================================
    // View Helpers
    // ============================================================

    /// @notice getAgent — returns full agent metadata
    function getAgent(bytes32 poolId) external view returns (AgentMetadata memory) {
        return agents[poolId];
    }

    function getAgentPrice(bytes32 poolId) external view returns (uint256 price) {
        BondingCurve memory curve = bondingCurves[poolId];
        if (!agents[poolId].exists) return 0;
        if (curve.maxSupply == 0) return uint256(curve.basePrice);
        uint256 fillRatio = (uint256(curve.currentSupply) * 1e18) / curve.maxSupply;
        return uint256(curve.basePrice) + (fillRatio * uint256(curve.priceRange)) / 1e18;
    }

    function getTreasuryHistory(bytes32 poolId) external view returns (TreasuryAction[] memory) {
        return treasuryHistory[poolId];
    }

    function getAgentByIndex(uint256 index) external view returns (bytes32) {
        require(index < allAgentPools.length, "ALH: index out");
        return allAgentPools[index];
    }

    function getPoolAgents(uint256 offset, uint256 limit) external view returns (bytes32[] memory ids, AgentMetadata[] memory meta) {
        uint256 len = allAgentPools.length;
        if (offset >= len) return (new bytes32[](0), new AgentMetadata[](0));
        uint256 end = offset + limit;
        if (end > len) end = len;
        uint256 count = end - offset;
        ids = new bytes32[](count);
        meta = new AgentMetadata[](count);
        for (uint256 i = 0; i < count; i++) {
            ids[i] = allAgentPools[offset + i];
            meta[i] = agents[ids[i]];
        }
    }

    // ============================================================
    // Internal
    // ============================================================

    function _distributeFees(bytes32 poolId, BalanceDelta delta) internal {
        AgentMetadata memory agent = agents[poolId];
        uint256 volume;

        int128 amt0 = delta.amount0();
        int128 amt1 = delta.amount1();

        if (amt0 != 0) {
            volume = uint128(amt0 < 0 ? uint128(-amt0) : uint128(amt0));
        } else if (amt1 != 0) {
            volume = uint128(amt1 < 0 ? uint128(-amt1) : uint128(amt1));
        } else {
            return;
        }

        uint256 feeAmount = (volume * uint256(agent.agentFee)) / FEE_DENOMINATOR;
        if (feeAmount == 0) return;

        uint256 devShare = (feeAmount * DEV_SHARE_BPS) / 10000;
        uint256 protocolShare = (feeAmount * PROTOCOL_SHARE_BPS) / 10000;
        uint256 lpShare = feeAmount - devShare - protocolShare;

        devBalances[poolId] += devShare;
        protocolBalances[poolId] += protocolShare;
        totalFeesCollected[poolId] += feeAmount;

        treasuryHistory[poolId].push(TreasuryAction({
            amount: feeAmount,
            devShare: devShare,
            protocolShare: protocolShare,
            timestamp: block.timestamp
        }));

        emit FeeDistributed(poolId, feeAmount, devShare, protocolShare, lpShare);
    }

    function _emitBondingEvent(bytes32 poolId, BondingCurve memory curve) internal {
        uint256 fillRatio = curve.maxSupply > 0
            ? (uint256(curve.currentSupply) * 1e18) / curve.maxSupply
            : 0;
        uint256 price = uint256(curve.basePrice) + (fillRatio * uint256(curve.priceRange)) / 1e18;
        emit BondingCurveUpdated(poolId, curve.currentSupply, uint128(price));
    }
}
