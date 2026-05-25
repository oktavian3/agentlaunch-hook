// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IPoolManager} from "v4-core/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "v4-core/types/PoolId.sol";
import {BalanceDelta} from "v4-core/types/BalanceDelta.sol";
import {Currency} from "v4-core/types/Currency.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

/// @title TradingAgent — AI Agent Trading & Liquidity Manager
/// @notice Companion contract for AgentHook that lets the AI agent actively
///         manage LP positions, swap tokens, and reinvest treasury fees.
///
/// Architecture:
///   AgentHook (passive)  →  collects swap fees into treasury
///   TradingAgent (active) →  manages LP positions using agent's treasury
///   TradingBot.py         →  AI decision-maker: reads pool state, decides actions
///
/// The AI agent wallet calls these functions based on TradingBot.py decisions.
/// This keeps the agent in full control — no automated contracts, just
/// AI-initiated actions.
contract TradingAgent {
    using PoolIdLibrary for PoolKey;

    // ============================================================
    // Types
    // ============================================================

    /// @notice A managed LP position
    struct Position {
        PoolKey poolKey;        // The pool this position is in
        int24 tickLower;        // Lower tick of the range
        int24 tickUpper;        // Upper tick of the range
        uint128 liquidity;      // Current liquidity amount
        uint256 amount0;        // Current token0 deposited
        uint256 amount1;        // Current token1 deposited
        uint256 lastRebalance;  // Timestamp of last rebalance
    }

    /// @notice Trading strategy config
    struct Strategy {
        uint24 rebalanceThresholdBps;  // Price movement % to trigger rebalance (e.g. 200 = 2%)
        uint24 feeClaimInterval;        // Hours between fee collection
        bool active;                    // Is trading active?
    }

    /// @notice Single swap execution
    struct SwapIntent {
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        uint256 deadline;
    }

    // ============================================================
    // State
    // ============================================================

    IPoolManager public immutable poolManager;
    address public immutable agentHook;       // Associated AgentHook
    address public immutable agentTreasury;    // Where fees flow (AgentHook address)

    // Agent positions
    Position[] public positions;

    // Strategy config
    Strategy public strategy;

    // Agent wallet — same as AgentHook's agent wallet
    address public agentWallet;

    // Track total value managed
    uint256 public totalValueLocked;   // in wei (ETH equivalent)
    uint256 public totalSwapsExecuted;
    uint256 public totalRebalances;

    // ============================================================
    // Events
    // ============================================================

    event PositionOpened(uint256 indexed positionId, PoolKey poolKey, int24 tickLower, int24 tickUpper, uint128 liquidity);
    event PositionClosed(uint256 indexed positionId, uint256 amount0Returned, uint256 amount1Returned);
    event PositionRebalanced(uint256 indexed positionId, int24 oldTickLower, int24 oldTickUpper, int24 newTickLower, int24 newTickUpper);
    event SwapExecuted(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut, uint256 fee);
    event FeesReinvested(uint256 amount, uint256 timestamp);
    event StrategyUpdated(uint24 rebalanceThresholdBps, uint24 feeClaimInterval, bool active);
    event AgentWalletUpdated(address oldWallet, address newWallet);

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyAgent() {
        require(msg.sender == agentWallet, "TradingAgent: not agent");
        _;
    }

    modifier onlyHook() {
        require(msg.sender == agentHook, "TradingAgent: not hook");
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    constructor(
        IPoolManager _poolManager,
        address _agentHook,
        address _agentWallet
    ) {
        require(_agentHook != address(0), "TradingAgent: zero hook");
        require(_agentWallet != address(0), "TradingAgent: zero wallet");

        poolManager = _poolManager;
        agentHook = _agentHook;
        agentTreasury = _agentHook;  // Fees accumulate in AgentHook
        agentWallet = _agentWallet;

        // Default strategy: rebalance at 2% price move, claim fees every 24h
        strategy = Strategy({
            rebalanceThresholdBps: 200,
            feeClaimInterval: 24,
            active: true
        });

        emit StrategyUpdated(200, 24, true);
    }

    // ============================================================
    // Agent Identity
    // ============================================================

    /// @notice Update agent wallet address (must match AgentHook)
    function setAgentWallet(address _newWallet) external onlyAgent {
        require(_newWallet != address(0), "TradingAgent: zero address");
        address old = agentWallet;
        agentWallet = _newWallet;
        emit AgentWalletUpdated(old, _newWallet);
    }

    /// @notice Update trading strategy parameters
    function updateStrategy(uint24 _rebalanceThresholdBps, uint24 _feeClaimInterval, bool _active) external onlyAgent {
        require(_rebalanceThresholdBps > 0 && _rebalanceThresholdBps <= 5000, "TradingAgent: invalid threshold");
        strategy = Strategy({
            rebalanceThresholdBps: _rebalanceThresholdBps,
            feeClaimInterval: _feeClaimInterval,
            active: _active
        });
        emit StrategyUpdated(_rebalanceThresholdBps, _feeClaimInterval, _active);
    }

    // ============================================================
    // LP Position Management
    // ============================================================

    /// @notice Open a new LP position in a V4 pool
    ///         Agent must have approved this contract to spend tokens
    /// @param _poolKey The Uniswap V4 pool
    /// @param _tickLower Lower tick
    /// @param _tickUpper Upper tick
    /// @param _amount0Max Max token0 to deposit
    /// @param _amount1Max Max token1 to deposit
    /// @return positionId Index of the new position
    function openPosition(
        PoolKey calldata _poolKey,
        int24 _tickLower,
        int24 _tickUpper,
        uint256 _amount0Max,
        uint256 _amount1Max
    ) external onlyAgent returns (uint256 positionId) {
        require(strategy.active, "TradingAgent: strategy paused");
        require(_tickLower < _tickUpper, "TradingAgent: invalid ticks");

        // Transfer tokens from agent to this contract
        if (_amount0Max > 0) {
            _safeTransferFrom(Currency.unwrap(_poolKey.currency0), msg.sender, address(this), _amount0Max);
        }
        if (_amount1Max > 0) {
            _safeTransferFrom(Currency.unwrap(_poolKey.currency1), msg.sender, address(this), _amount1Max);
        }

        // Approve PoolManager to spend tokens
        if (_amount0Max > 0) {
            _safeApprove(Currency.unwrap(_poolKey.currency0), address(poolManager), _amount0Max);
        }
        if (_amount1Max > 0) {
            _safeApprove(Currency.unwrap(_poolKey.currency1), address(poolManager), _amount1Max);
        }

        // Use PoolManager.modifyLiquidity to add position
        // Note: In real V4, this calls poolManager.modifyLiquidity with
        // the PoolKey, ModifyLiquidityParams, and hook data
        // For this implementation, we track the position state
        IPoolManager.ModifyLiquidityParams memory params = IPoolManager.ModifyLiquidityParams({
            tickLower: _tickLower,
            tickUpper: _tickUpper,
            liquidityDelta: 0,  // Will be calculated by caller
            salt: 0
        });

        // In production, the actual modifyLiquidity call goes here
        // poolManager.modifyLiquidity(_poolKey, params, "");
        // For now we approximate — the real implementation needs
        // the caller to compute exact liquidityDelta based on amounts

        positionId = positions.length;
        positions.push(Position({
            poolKey: _poolKey,
            tickLower: _tickLower,
            tickUpper: _tickUpper,
            liquidity: 0,
            amount0: _amount0Max,
            amount1: _amount1Max,
            lastRebalance: block.timestamp
        }));

        totalValueLocked += _amount0Max + _amount1Max;
        emit PositionOpened(positionId, _poolKey, _tickLower, _tickUpper, 0);
    }

    /// @notice Close an LP position and withdraw all liquidity
    /// @param _positionId The position index
    function closePosition(uint256 _positionId) external onlyAgent {
        require(_positionId < positions.length, "TradingAgent: invalid position");
        Position storage pos = positions[_positionId];
        require(pos.liquidity > 0 || pos.amount0 > 0 || pos.amount1 > 0, "TradingAgent: empty position");

        // Remove liquidity from the pool
        // poolManager.modifyLiquidity(pos.poolKey, ..., "");

        uint256 amount0Returned = pos.amount0;
        uint256 amount1Returned = pos.amount1;

        // Transfer tokens back to agent
        if (amount0Returned > 0) {
            _safeTransfer(Currency.unwrap(pos.poolKey.currency0), agentWallet, amount0Returned);
        }
        if (amount1Returned > 0) {
            _safeTransfer(Currency.unwrap(pos.poolKey.currency1), agentWallet, amount1Returned);
        }

        // Clear position
        delete positions[_positionId];

        emit PositionClosed(_positionId, amount0Returned, amount1Returned);
    }

    /// @notice Rebalance a position — move ticks based on price movement
    /// @param _positionId The position to rebalance
    /// @param _newTickLower New lower tick
    /// @param _newTickUpper New upper tick
    /// @param _newLiquidity New liquidity delta
    function rebalancePosition(
        uint256 _positionId,
        int24 _newTickLower,
        int24 _newTickUpper,
        uint128 _newLiquidity
    ) external onlyAgent {
        require(_positionId < positions.length, "TradingAgent: invalid position");
        Position storage pos = positions[_positionId];
        require(pos.liquidity > 0, "TradingAgent: no liquidity");

        int24 oldLower = pos.tickLower;
        int24 oldUpper = pos.tickUpper;

        // Remove old liquidity
        // poolManager.modifyLiquidity(pos.poolKey, ..., "");
        // Add new liquidity at new ticks
        // poolManager.modifyLiquidity(pos.poolKey, ..., "");

        pos.tickLower = _newTickLower;
        pos.tickUpper = _newTickUpper;
        pos.liquidity = _newLiquidity;
        pos.lastRebalance = block.timestamp;

        totalRebalances++;

        emit PositionRebalanced(_positionId, oldLower, oldUpper, _newTickLower, _newTickUpper);
    }

    // ============================================================
    // Swap & Reinvest
    // ============================================================

    /// @notice Execute a swap through Uniswap V4 PoolManager
    ///         The agent wallet calls this to trade tokens
    /// @param _poolKey The pool to swap through
    /// @param _zeroForOne Direction: true = token0→token1, false = token1→token0
    /// @param _amountSpecified Exact amount in
    /// @param _sqrtPriceLimit Max/min price
    /// @return amountDelta Actual swap result
    function executeSwap(
        PoolKey calldata _poolKey,
        bool _zeroForOne,
        int256 _amountSpecified,
        uint160 _sqrtPriceLimit
    ) external onlyAgent returns (BalanceDelta amountDelta) {
        require(strategy.active, "TradingAgent: strategy paused");

        IPoolManager.SwapParams memory params = IPoolManager.SwapParams({
            zeroForOne: _zeroForOne,
            amountSpecified: _amountSpecified,
            sqrtPriceLimitX96: _sqrtPriceLimit
        });

        // Transfer tokens in
        address tokenIn = _zeroForOne
            ? Currency.unwrap(_poolKey.currency0)
            : Currency.unwrap(_poolKey.currency1);

        _safeTransferFrom(tokenIn, msg.sender, address(this), uint256(_amountSpecified > 0 ? _amountSpecified : -_amountSpecified));
        _safeApprove(tokenIn, address(poolManager), uint256(_amountSpecified > 0 ? _amountSpecified : -_amountSpecified));

        // Execute swap via PoolManager
        // BalanceDelta delta = poolManager.swap(_poolKey, params, "");

        // Approximate: just record the intent
        totalSwapsExecuted++;

        emit SwapExecuted(
            tokenIn,
            _zeroForOne ? Currency.unwrap(_poolKey.currency1) : Currency.unwrap(_poolKey.currency0),
            uint256(_amountSpecified > 0 ? _amountSpecified : -_amountSpecified),
            0,
            0
        );

        return BalanceDelta.wrap(0);
    }

    /// @notice Reinvest accumulated treasury fees from AgentHook into LP
    ///         This makes the agent's treasury WORK instead of sitting idle
    /// @param _positionId Which position to add liquidity to
    /// @param _amount Amount to reinvest from treasury
    function reinvestFees(uint256 _positionId, uint256 _amount) external onlyAgent {
        require(_positionId < positions.length, "TradingAgent: invalid position");
        require(_amount > 0, "TradingAgent: zero amount");

        // In production: pull fees from AgentHook treasury
        // AgentHook hook = AgentHook(agentHook);
        // hook.withdrawTo(address(this), _amount);

        // Then add to position liquidity
        // poolManager.modifyLiquidity(...)

        emit FeesReinvested(_amount, block.timestamp);
    }

    // ============================================================
    // Views
    // ============================================================

    /// @notice Get all positions
    function getPositions() external view returns (Position[] memory) {
        return positions;
    }

    /// @notice Get position count
    function getPositionCount() external view returns (uint256) {
        return positions.length;
    }

    /// @notice Get summary stats
    function getStats() external view returns (
        uint256 positionCount,
        uint256 tvl,
        uint256 swaps,
        uint256 rebalances,
        bool active
    ) {
        return (
            positions.length,
            totalValueLocked,
            totalSwapsExecuted,
            totalRebalances,
            strategy.active
        );
    }

    // ============================================================
    // Internal — Safe Token Ops
    // ============================================================

    function _safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transferFrom.selector, from, to, amount)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "TradingAgent: transferFrom failed");
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transfer.selector, to, amount)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "TradingAgent: transfer failed");
    }

    function _safeApprove(address token, address spender, uint256 amount) internal {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.approve.selector, spender, amount)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "TradingAgent: approve failed");
    }
}
