#!/usr/bin/env python3
"""
get_pool_key.py — Generate a Uniswap V4 PoolKey Hash

Uniswap V4 uses PoolKey to identify pools. A PoolKey consists of:
  - currency0 (address): the lower-sorted token address
  - currency1 (address): the higher-sorted token address
  - fee (uint24): the fee tier (LP fee, 0-1000000)
  - tickSpacing (int24): determines tradable price range
  - hooks (address): the Hook contract address

Usage:
  python3 scripts/get_pool_key.py <token0> <token1> <fee> <hooks_address>

Examples:
  # USDC/WETH pool with SoulAgent Hook, 0.30% fee
  python3 scripts/get_pool_key.py \\
    0x74b7f16337b4e1f1C4f2cC2eC93C94A3bCb2C3A \\
    0x5B5dee44552546ECEA05EDeA01DCD7Be7aa61421 \\
    3000 \\
    0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749

  # XRP/WETH pool, 0.05% fee
  python3 scripts/get_pool_key.py \\
    0xC33D8A1dC4Cf07f7A3F94D38F39d7B4Bf2c6cB3a \\
    0x5B5dee44552546ECEA05EDeA01DCD7Be7aa61421 \\
    500 \\
    0x3ad2A07A4C021ccC64ccF6c1B5ce8181AF9eA749

Output:
  PoolKey hash (bytes32 hex): 0xabc123...
  Pool ID (decoded): 0xabc... (same value)

Use this hash to:
  1. Set POOL_KEY in your keeper bot environment
  2. Verify the pool on the dashboard
  3. Look up pool state via the Uniswap V4 PoolManager
"""

import sys
from hashlib import sha256


def sort_tokens(addr0, addr1):
    """Sort token addresses — Uniswap V4 requires currency0 < currency1."""
    a0 = addr0.lower()
    a1 = addr1.lower()
    if a0 < a1:
        return a0, a1
    return a1, a0


def encode_pool_key(token0, token1, fee, tick_spacing, hooks):
    """
    Encode a Uniswap V4 PoolKey and return its bytes32 hash.
    
    PoolKey packing (tight):
      currency0:  20 bytes (address)
      currency1:  20 bytes (address)
      fee:        3 bytes (uint24)
      tickSpacing: 3 bytes padded? Actually int24 packed
      hooks:      20 bytes (address)
    
    In Solidity PoolKey is a struct, and .toId() computes:
      keccak256(abi.encode(PoolKey))
    
    We replicate that here.
    """
    # For ABI encoding: (address, address, uint24, int24, address)
    # We need to simulate abi.encode()
    from eth_hash.auto import keccak
    
    # Remove 0x prefix if present
    t0 = bytes.fromhex(token0.replace('0x', '').zfill(40))
    t1 = bytes.fromhex(token1.replace('0x', '').zfill(40))
    h = bytes.fromhex(hooks.replace('0x', '').zfill(40))
    
    # ABI encode: address(32 bytes each), uint24(32 bytes), int24(32 bytes), address(32 bytes)
    # But abi.encode packs tightly for structs... actually abi.encode pads each to 32 bytes
    
    # Simpler: use the Solidity-style encoding
    import struct
    
    # Build the packed struct
    # PoolKey memory: currency0(20) + currency1(20) + fee(3) + tickSpacing(3) + hooks(20)
    # But abi.encode pads each element to 32 bytes for hash
    padded = (
        b'\x00' * 12 + t0 +  # address -> 32 bytes
        b'\x00' * 12 + t1 +  # address -> 32 bytes
        b'\x00' * 29 + struct.pack('>I', fee)[1:4] +  # uint24 -> 32 bytes
        b'\x00' * 29 + struct.pack('>i', tick_spacing)[1:4] +  # int24 -> 32 bytes
        b'\x00' * 12 + h     # address -> 32 bytes
    )
    
    hash_bytes = keccak(padded)
    return '0x' + hash_bytes.hex()


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    
    token0 = sys.argv[1]
    token1 = sys.argv[2]
    fee = int(sys.argv[3])
    hooks = sys.argv[4]
    tick_spacing = int(sys.argv[5]) if len(sys.argv) > 5 else 60  # default 60 for 0.30%
    
    # Sort tokens
    t0, t1 = sort_tokens(token0, token1)
    
    if t0 != token0.lower():
        print(f"⚠️  Tokens re-sorted: {token0} <-> {token1}")
        token0, token1 = '0x' + t0, '0x' + t1
    
    pool_key = encode_pool_key(token0, token1, fee, tick_spacing, hooks)
    
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  PoolKey Generator")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Token0:    {token0}")
    print(f"  Token1:    {token1}")
    print(f"  Fee:       {fee} ({fee/10000:.4f}%)")
    print(f"  Tick:      ±{tick_spacing}")
    print(f"  Hook:      {hooks}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  POOL_KEY={pool_key}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print(f"  Add to your .env:")
    print(f"  POOL_KEY={pool_key}")
    print()
    print(f"  Or find it on-chain:")
    print(f"  curl https://rpc.xlayer.tech -X POST -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"jsonrpc\":\"2.0\",\"method\":\"eth_call\",\"params\":[{{\"to\":\"0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32\",\"data\":\"0x...\"}},\"latest\"],\"id\":1}}'")


if __name__ == '__main__':
    # Check for eth-hash
    try:
        from eth_hash.auto import keccak
    except ImportError:
        print("ERROR: eth-hash not installed. Run: pip install eth-hash pycryptodome")
        sys.exit(1)
    
    main()
