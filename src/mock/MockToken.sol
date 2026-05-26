// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;
import {ERC20} from "openzeppelin-contracts/contracts/token/ERC20/ERC20.sol";
contract MockERC20 is ERC20("Demo USDC", "dUSDC") {
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}
