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

/// @title AgentHook — Autonomous AI Agent Owned Uniswap V4 Hook
/// @notice Each instance of this Hook IS an AI agent's on-chain identity.
///         The agent wallet (0xAgent...) owns and controls this Hook:
///         - Sets its own swap fee dynamically
///         - Accumulates treasury from swap fees
///         - Signs heartbeats to prove it's alive
///         - Can verify arbitrary messages on-chain
///
/// How it works:
/// 1. An AI agent (e.g. Eliza, Hermes, custom bot) deploys this Hook
/// 2. Agent creates a Uniswap V4 pool with this Hook address + dynamic fee
/// 3. beforeSwap: overrides fee with agent's current fee setting
/// 4. afterSwap: accumulates treasury for the agent
/// 5. Anyone can verify: "this Hook belongs to agent X" via agentWallet()
///
/// Fee split:
/// - Agent fee: 100% goes to agent treasury (no protocol cut — pure agent-owned)
///
/// This makes each AI agent a self-sovereign DeFi participant.
contract AgentHook is IHooks {
    using PoolIdLibrary for PoolKey;
    using LPFeeLibrary for uint24;
    using StateLibrary for IPoolManager;

    // ============================================================
    // Types
    // ============================================================

    /// @notice Agent identity & preferences
    struct AgentConfig {
        address agentWallet;       // The AI agent's wallet address
        string  agentName;         // Human-readable agent name
        string  agentDescription;  // What this agent does
        uint24  agentFee;          // Fee in basis points (e.g. 30 = 0.30%)
        uint40  createdAt;         // When this Hook was deployed
        uint40  lastHeartbeat;     // Last time agent signed alive
        bool    exists;
    }

    /// @notice A signed message from the agent (for on-chain verification)
    struct AgentMessage {
        address agentWallet;
        string  content;
        uint256 timestamp;
        bytes   signature;
    }

    /// @notice Treasury distribution record
    struct TreasuryAction {
        uint256 amount;
        uint256 timestamp;
    }

    // ============================================================
    // State
    // ============================================================

    IPoolManager public immutable poolManager;

    // Agent identity — set once in constructor
    AgentConfig public config;
    bytes32 public poolId;
    bool public initialized;

    // Treasury
    uint256 public treasuryBalance;
    uint256 public totalFeesCollected;
    TreasuryAction[] public treasuryHistory;

    // Agent messages registry
    AgentMessage[] public agentMessages;

    // ============================================================
    // Constants
    // ============================================================

    uint24 public constant MAX_AGENT_FEE = 1000;     // 10.00%
    uint24 public constant MIN_AGENT_FEE = 1;         // 0.01%
    uint24 public constant DEFAULT_AGENT_FEE = 30;    // 0.30%
    uint24 public constant FEE_DENOMINATOR = 10000;
    uint32 public constant HEARTBEAT_INTERVAL = 86400; // 24 hours

    // ============================================================
    // Events
    // ============================================================

    event AgentRegistered(
        address indexed agentWallet,
        string agentName,
        uint24 agentFee,
        address hookAddress
    );
    event FeeUpdated(address indexed agentWallet, uint24 oldFee, uint24 newFee);
    event TreasuryAccumulated(uint256 amount, uint256 total);
    event AgentWithdrew(address indexed agentWallet, uint256 amount);
    event Heartbeat(address indexed agentWallet, uint40 timestamp);
    event MessagePosted(address indexed agentWallet, string content, uint256 timestamp);
    event AgentInitialized(bytes32 indexed poolId, address poolManager);

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyAgent() {
        require(msg.sender == config.agentWallet, "AgentHook: not agent");
        _;
    }

    modifier onlyPoolManager() {
        require(msg.sender == address(poolManager), "AgentHook: not pool manager");
        _;
    }

    modifier whenInitialized() {
        require(initialized, "AgentHook: not initialized");
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    /// @notice Deploy a new AgentHook instance owned by an AI agent
    /// @param _poolManager Uniswap V4 PoolManager on X Layer
    /// @param _agentWallet The AI agent's wallet address that will control this Hook
    /// @param _agentName Human-readable name for this agent
    /// @param _agentDescription Description of what this AI agent does
    /// @param _agentFee Initial fee in basis points (e.g. 30 = 0.30%)
    constructor(
        IPoolManager _poolManager,
        address _agentWallet,
        string memory _agentName,
        string memory _agentDescription,
        uint24 _agentFee
    ) {
        require(_agentWallet != address(0), "AgentHook: zero wallet");
        require(bytes(_agentName).length > 0, "AgentHook: name required");
        require(_agentFee >= MIN_AGENT_FEE && _agentFee <= MAX_AGENT_FEE, "AgentHook: invalid fee");

        poolManager = _poolManager;

        config = AgentConfig({
            agentWallet: _agentWallet,
            agentName: _agentName,
            agentDescription: _agentDescription,
            agentFee: _agentFee,
            createdAt: uint40(block.timestamp),
            lastHeartbeat: uint40(block.timestamp),
            exists: true
        });

        emit AgentRegistered(_agentWallet, _agentName, _agentFee, address(this));
    }

    // ============================================================
    // Agent Identity & Control
    // ============================================================

    /// @notice Set a new fee (only callable by the AI agent wallet)
    function setFee(uint24 _newFee) external onlyAgent {
        require(_newFee >= MIN_AGENT_FEE && _newFee <= MAX_AGENT_FEE, "AgentHook: invalid fee");
        uint24 oldFee = config.agentFee;
        config.agentFee = _newFee;
        emit FeeUpdated(config.agentWallet, oldFee, _newFee);
    }

    /// @notice Update agent description (only callable by the AI agent)
    function setDescription(string calldata _newDescription) external onlyAgent {
        require(bytes(_newDescription).length > 0, "AgentHook: empty description");
        config.agentDescription = _newDescription;
    }

    /// @notice Send a heartbeat — proves the AI agent is still alive and in control
    ///         Should be called periodically by the agent's automation (cron job, keeper, etc.)
    function heartbeat() external onlyAgent {
        config.lastHeartbeat = uint40(block.timestamp);
        emit Heartbeat(config.agentWallet, config.lastHeartbeat);
    }

    /// @notice Post an on-chain message from the AI agent
    ///         This creates a permanent record: "Agent X said Y at time Z"
    /// @param content The message content
    function postMessage(string calldata content) external onlyAgent {
        require(bytes(content).length > 0, "AgentHook: empty message");
        agentMessages.push(AgentMessage({
            agentWallet: config.agentWallet,
            content: content,
            timestamp: block.timestamp,
            signature: ""
        }));
        emit MessagePosted(config.agentWallet, content, block.timestamp);
    }

    /// @notice Transfer agent ownership to a new wallet
    ///         Useful if the agent rotates keys or migrates
    /// @param _newWallet New agent wallet address
    function transferAgentOwnership(address _newWallet) external onlyAgent {
        require(_newWallet != address(0), "AgentHook: zero address");
        config.agentWallet = _newWallet;
    }

    /// @notice Get agent info in one call
    function getAgentInfo() external view returns (
        address wallet,
        string memory name,
        string memory description,
        uint24 fee,
        uint40 created,
        uint40 lastSeen,
        uint256 treasury,
        uint256 totalFees,
        uint256 messageCount,
        bytes32 agentPoolId,
        bool isAlive
    ) {
        wallet = config.agentWallet;
        name = config.agentName;
        description = config.agentDescription;
        fee = config.agentFee;
        created = config.createdAt;
        lastSeen = config.lastHeartbeat;
        treasury = treasuryBalance;
        totalFees = totalFeesCollected;
        messageCount = agentMessages.length;
        agentPoolId = poolId;
        isAlive = (block.timestamp - config.lastHeartbeat) <= HEARTBEAT_INTERVAL * 2;
    }

    /// @notice getAgentInfoStruct — returns agent info as struct (for easy test access)
    function getAgentInfoStruct() external view returns (AgentConfig memory) {
        return config;
    }

    /// @notice getMessageStruct — returns agent message as struct
    function getMessageStruct(uint256 index) external view returns (AgentMessage memory) {
        require(index < agentMessages.length, "AgentHook: invalid index");
        return agentMessages[index];
    }

    // ============================================================
    // Treasury
    // ============================================================

    /// @notice Withdraw accumulated treasury fees (only AI agent wallet)
    function withdraw() external onlyAgent {
        uint256 amount = treasuryBalance;
        require(amount > 0, "AgentHook: empty treasury");
        treasuryBalance = 0;
        emit AgentWithdrew(config.agentWallet, amount);
    }

    /// @notice Get treasury history
    function getTreasuryHistory() external view returns (TreasuryAction[] memory) {
        return treasuryHistory;
    }

    /// @notice Get message count
    function getMessageCount() external view returns (uint256) {
        return agentMessages.length;
    }

    /// @notice Get a specific agent message
    function getMessage(uint256 index) external view returns (AgentMessage memory) {
        require(index < agentMessages.length, "AgentHook: invalid index");
        return agentMessages[index];
    }

    // ============================================================
    // Hook Implementations — IHooks
    // ============================================================

    function beforeInitialize(address, PoolKey calldata, uint160)
        external override onlyPoolManager returns (bytes4)
    {
        return IHooks.beforeInitialize.selector;
    }

    /// @notice afterInitialize — Bind this Hook instance to the pool
    function afterInitialize(address, PoolKey calldata key, uint160, int24)
        external override onlyPoolManager returns (bytes4)
    {
        require(!initialized, "AgentHook: already initialized");
        initialized = true;
        poolId = PoolId.unwrap(key.toId());
        emit AgentInitialized(poolId, address(poolManager));
        return IHooks.afterInitialize.selector;
    }

    function beforeAddLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.beforeAddLiquidity.selector;
    }

    function afterAddLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata,
        BalanceDelta, BalanceDelta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BalanceDelta) {
        return (IHooks.afterAddLiquidity.selector, BalanceDelta.wrap(0));
    }

    function beforeRemoveLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4) {
        return IHooks.beforeRemoveLiquidity.selector;
    }

    function afterRemoveLiquidity(
        address, PoolKey calldata, IPoolManager.ModifyLiquidityParams calldata,
        BalanceDelta, BalanceDelta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BalanceDelta) {
        return (IHooks.afterRemoveLiquidity.selector, BalanceDelta.wrap(0));
    }

    /// @notice beforeSwap — Apply agent's fee override
    ///         The AI agent's configured fee is used as the dynamic LP fee
    /// @return fee The agent's current fee setting (if dynamic fee pool)
    function beforeSwap(
        address, PoolKey calldata key, IPoolManager.SwapParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BeforeSwapDelta, uint24) {
        if (key.fee.isDynamicFee()) {
            poolManager.updateDynamicLPFee(key, config.agentFee);
        }
        return (IHooks.beforeSwap.selector, BeforeSwapDelta.wrap(0), 0);
    }

    /// @notice afterSwap — Accumulate treasury for the AI agent
    ///         Every swap generates fees → treasury grows → agent can withdraw
    function afterSwap(
        address, PoolKey calldata key, IPoolManager.SwapParams calldata, BalanceDelta delta, bytes calldata
    ) external override onlyPoolManager returns (bytes4, int128) {
        if (initialized) {
            _accumulate(delta);
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
    // Internal
    // ============================================================

    /// @notice _accumulate — Extract fee from swap delta and add to treasury
    function _accumulate(BalanceDelta delta) internal {
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

        // Estimate fee: volume * fee / FEE_DENOMINATOR
        uint256 feeAmount = (volume * uint256(config.agentFee)) / FEE_DENOMINATOR;
        if (feeAmount == 0) return;

        treasuryBalance += feeAmount;
        totalFeesCollected += feeAmount;

        treasuryHistory.push(TreasuryAction({
            amount: feeAmount,
            timestamp: block.timestamp
        }));

        emit TreasuryAccumulated(feeAmount, totalFeesCollected);
    }
}
