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
import {Currency} from "v4-core/types/Currency.sol";

/// @title AgentYieldHook — AI-Managed Yield Engine on Uniswap V4
/// @notice Each instance is an AI agent's on-chain yield vault.
///         Users deposit LP tokens → Hook stakes into V4 pool →
///         AI bot reinvests treasury fees → auto-compound yield.
contract AgentYieldHook is IHooks {
    using PoolIdLibrary for PoolKey;
    using LPFeeLibrary for uint24;
    using StateLibrary for IPoolManager;

    // ============================================================
    // Types
    // ============================================================

    /// @notice User deposit share
    struct VaultShare {
        uint256 amount;
        uint256 depositedAt;
    }

    /// @notice Strategy configuration
    enum StrategyMode { Aggressive, Balanced, Conservative }

    struct StrategyConfig {
        StrategyMode mode;
        uint24 fee;
        int24 tickRange;
        string description;
    }

    // ============================================================
    // State
    // ============================================================

    IPoolManager public immutable poolManager;
    address public immutable factory;

    string public agentName;
    address public agentWallet;
    bool public initialized;

    uint256 public totalDeposits;
    uint256 public treasuryBalance;
    uint256 public totalFeesCollected;
    uint256 public lastReinvestTime;

    PoolKey public poolKey;
    bytes32 public poolId;

    StrategyConfig public strategy;
    int24 public currentTickLower;
    int24 public currentTickUpper;
    uint128 public currentLiquidity;

    mapping(address => VaultShare) public depositors;
    address[] public depositorList;
    string[] public agentMessages;

    // ============================================================
    // Constants
    // ============================================================

    uint24 public constant MAX_FEE = 1000;
    uint24 public constant MIN_FEE = 1;
    uint24 public constant FEE_DENOM = 10000;
    uint32 public constant REINVEST_COOLDOWN = 3600;
    uint256 public constant DEPOSIT_FEE_BPS = 10;
    uint256 public constant PERFORMANCE_FEE_BPS = 1000;

    function getStrategyConfig(StrategyMode mode) internal pure returns (StrategyConfig memory) {
        if (mode == StrategyMode.Aggressive) {
            return StrategyConfig(mode, 1, 100, "Aggressive - narrow range, max yield");
        } else if (mode == StrategyMode.Balanced) {
            return StrategyConfig(mode, 30, 600, "Balanced - medium range, stable");
        } else {
            return StrategyConfig(mode, 100, 2000, "Conservative - wide range, capital protection");
        }
    }

    // ============================================================
    // Events
    // ============================================================

    event Deposited(address indexed user, uint256 amount, uint256 totalDeposits);
    event Withdrawn(address indexed user, uint256 amount, uint256 yieldEarned);
    event TreasuryAccumulated(uint256 amount, uint256 total);
    event Reinvested(uint256 amount, uint128 newLiquidity, uint256 timestamp);
    event FeeUpdated(uint24 oldFee, uint24 newFee);
    event ModeChanged(StrategyMode oldMode, StrategyMode newMode);
    event AgentMessagePosted(string content, uint256 timestamp);

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyAgent() {
        require(msg.sender == agentWallet, "AY: not agent");
        _;
    }

    modifier onlyFactory() {
        require(msg.sender == factory, "AY: not factory");
        _;
    }

    modifier onlyPoolManager() {
        require(msg.sender == address(poolManager), "AY: not pool manager");
        _;
    }

    modifier whenInitialized() {
        require(initialized, "AY: not init");
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    constructor(
        IPoolManager _poolManager,
        address _agentWallet,
        string memory _name,
        StrategyMode _mode
    ) {
        require(_agentWallet != address(0), "AY: zero wallet");
        require(bytes(_name).length > 0, "AY: name required");

        poolManager = _poolManager;
        factory = msg.sender;
        agentWallet = _agentWallet;
        agentName = _name;
        strategy = getStrategyConfig(_mode);
    }

    // ============================================================
    // Factory-only
    // ============================================================

    function initialize(PoolKey calldata _key) external onlyFactory {
        require(!initialized, "AY: already init");
        initialized = true;
        poolKey = _key;
        poolId = PoolId.unwrap(_key.toId());
        currentTickLower = -strategy.tickRange;
        currentTickUpper = strategy.tickRange;
    }

    // ============================================================
    // User Actions
    // ============================================================

    function deposit(uint256 amount) external {
        require(amount > 0, "AY: zero amount");
        require(initialized, "AY: not init");

        uint256 depositFee = (amount * DEPOSIT_FEE_BPS) / FEE_DENOM;
        uint256 netAmount = amount - depositFee;

        VaultShare storage share = depositors[msg.sender];
        if (share.amount == 0) {
            depositorList.push(msg.sender);
        }

        share.amount += netAmount;
        share.depositedAt = block.timestamp;
        totalDeposits += netAmount;
        treasuryBalance += depositFee;

        emit Deposited(msg.sender, netAmount, totalDeposits);
    }

    function withdraw(uint256 amount) external {
        VaultShare storage share = depositors[msg.sender];
        require(share.amount > 0, "AY: no deposit");
        require(amount <= share.amount, "AY: exceeds balance");

        if (amount == 0) {
            amount = share.amount;
        }

        uint256 yieldEarned = _calculateYield(msg.sender, amount);
        uint256 perfFee = (yieldEarned * PERFORMANCE_FEE_BPS) / FEE_DENOM;
        uint256 userYield = yieldEarned - perfFee;

        share.amount -= amount;
        totalDeposits -= amount;
        treasuryBalance += perfFee;

        emit Withdrawn(msg.sender, amount, userYield);

        if (share.amount == 0) {
            _removeDepositor(msg.sender);
        }
    }

    // ============================================================
    // Agent Controls
    // ============================================================

    function reinvest() external onlyAgent whenInitialized {
        require(treasuryBalance > 0, "AY: empty treasury");
        require(block.timestamp >= lastReinvestTime + REINVEST_COOLDOWN, "AY: cooldown");

        uint256 amount = treasuryBalance;
        treasuryBalance = 0;
        lastReinvestTime = block.timestamp;

        currentLiquidity += uint128(amount / 1e12);

        emit Reinvested(amount, currentLiquidity, block.timestamp);
    }

    function setMode(StrategyMode _newMode) external onlyAgent {
        StrategyMode old = strategy.mode;
        strategy = getStrategyConfig(_newMode);
        emit ModeChanged(old, _newMode);
        emit FeeUpdated(strategy.fee, strategy.fee);
    }

    function setFee(uint24 _newFee) external onlyAgent {
        require(_newFee >= MIN_FEE && _newFee <= MAX_FEE, "AY: invalid fee");
        uint24 old = strategy.fee;
        strategy.fee = _newFee;
        emit FeeUpdated(old, _newFee);
    }

    function postMessage(string calldata content) external onlyAgent {
        agentMessages.push(content);
        emit AgentMessagePosted(content, block.timestamp);
    }

    function transferOwnership(address _newWallet) external onlyAgent {
        require(_newWallet != address(0), "AY: zero address");
        agentWallet = _newWallet;
    }

    function rebalancePosition(int24 _newLower, int24 _newUpper) external onlyAgent {
        require(_newLower < _newUpper, "AY: invalid ticks");
        currentTickLower = _newLower;
        currentTickUpper = _newUpper;
    }

    // ============================================================
    // Uniswap V4 Hook Callbacks
    // ============================================================

    function beforeInitialize(address, PoolKey calldata, uint160)
        external override onlyPoolManager returns (bytes4)
    {
        return IHooks.beforeInitialize.selector;
    }

    function afterInitialize(address, PoolKey calldata, uint160, int24)
        external override onlyPoolManager returns (bytes4)
    {
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

    function beforeSwap(
        address, PoolKey calldata key, IPoolManager.SwapParams calldata, bytes calldata
    ) external override onlyPoolManager returns (bytes4, BeforeSwapDelta, uint24) {
        if (key.fee.isDynamicFee()) {
            poolManager.updateDynamicLPFee(key, strategy.fee);
        }
        return (IHooks.beforeSwap.selector, BeforeSwapDelta.wrap(0), 0);
    }

    function afterSwap(
        address, PoolKey calldata, IPoolManager.SwapParams calldata, BalanceDelta delta, bytes calldata
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
    // View Functions
    // ============================================================

    function getAgentInfo() external view returns (
        string memory name,
        address wallet,
        uint256 tvl,
        uint256 treasury,
        uint256 totalFees,
        uint256 depositorCount,
        uint256 msgCount,
        StrategyMode mode,
        uint24 fee,
        uint128 liquidity,
        bool alive
    ) {
        return (
            agentName,
            agentWallet,
            totalDeposits,
            treasuryBalance,
            totalFeesCollected,
            depositorList.length,
            agentMessages.length,
            strategy.mode,
            strategy.fee,
            currentLiquidity,
            initialized
        );
    }

    function getMessageCount() external view returns (uint256) {
        return agentMessages.length;
    }

    function getMessage(uint256 index) external view returns (string memory) {
        require(index < agentMessages.length, "AY: invalid index");
        return agentMessages[index];
    }

    function getAllMessages() external view returns (string[] memory) {
        return agentMessages;
    }

    function getDepositorCount() external view returns (uint256) {
        return depositorList.length;
    }

    function getDepositorInfo(address user) external view returns (uint256 amount, uint256 depositedAt) {
        VaultShare storage s = depositors[user];
        return (s.amount, s.depositedAt);
    }

    function estimatedAPY() external view returns (uint256) {
        if (totalDeposits == 0 || totalFeesCollected == 0) return 0;
        return (totalFeesCollected * 10000) / totalDeposits;
    }

    // ============================================================
    // Internal
    // ============================================================

    function _accumulate(BalanceDelta delta) internal {
        int128 amt0 = delta.amount0();
        int128 amt1 = delta.amount1();

        uint256 volume;
        if (amt0 != 0) {
            volume = uint128(amt0 < 0 ? uint128(-amt0) : uint128(amt0));
        } else if (amt1 != 0) {
            volume = uint128(amt1 < 0 ? uint128(-amt1) : uint128(amt1));
        } else {
            return;
        }

        uint256 feeAmount = (volume * uint256(strategy.fee)) / FEE_DENOM;
        if (feeAmount == 0) return;

        treasuryBalance += feeAmount;
        totalFeesCollected += feeAmount;

        emit TreasuryAccumulated(feeAmount, totalFeesCollected);
    }

    function _calculateYield(address user, uint256 withdrawAmount) internal view returns (uint256) {
        VaultShare storage share = depositors[user];
        if (totalFeesCollected == 0 || totalDeposits == 0) return 0;

        uint256 userShareBps = (share.amount * 10000) / totalDeposits;
        uint256 yieldAmount = (totalFeesCollected * userShareBps) / 10000;

        if (withdrawAmount < share.amount) {
            yieldAmount = (yieldAmount * withdrawAmount) / share.amount;
        }

        return yieldAmount;
    }

    function _removeDepositor(address user) internal {
        for (uint256 i = 0; i < depositorList.length; i++) {
            if (depositorList[i] == user) {
                depositorList[i] = depositorList[depositorList.length - 1];
                depositorList.pop();
                return;
            }
        }
    }
}
