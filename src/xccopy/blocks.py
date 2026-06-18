"""Splitting an object into fixed-size transfer blocks.

A :class:`Block` is cloud-neutral (index/offset/length only); cloud-specific ids
(e.g. Azure block ids) are derived by the sink. ``plan_blocks`` chooses an adaptive
block size so Azure's 50,000-block limit is never exceeded (research D6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_BLOCK_SIZE = 8 * 1024 * 1024  # 8 MiB
MAX_BLOCK_SIZE = 4000 * 1024 * 1024  # Azure per-block maximum
MAX_BLOCKS = 50_000  # Azure per-blob block-count maximum
_MiB = 1024 * 1024


@dataclass(frozen=True)
class Block:
    """One transfer unit: a byte range of the source object."""

    index: int
    offset: int
    length: int


@dataclass(frozen=True)
class BlockPlan:
    """The full split of an object into ordered blocks."""

    block_size: int
    total_size: int
    blocks: tuple[Block, ...]

    @property
    def count(self) -> int:
        return len(self.blocks)


def _round_up_to_mib(n: int) -> int:
    return math.ceil(n / _MiB) * _MiB


def choose_block_size(total_size: int) -> int:
    """Pick the smallest block size (≥ default, MiB-aligned) that keeps the block
    count within Azure's limit for ``total_size``."""
    if total_size <= 0:
        return DEFAULT_BLOCK_SIZE
    block_size = DEFAULT_BLOCK_SIZE
    if math.ceil(total_size / block_size) > MAX_BLOCKS:
        block_size = _round_up_to_mib(math.ceil(total_size / MAX_BLOCKS))
    if block_size > MAX_BLOCK_SIZE:
        raise ValueError(
            f"Object of {total_size} bytes is too large to transfer: even at the maximum "
            f"block size it would exceed {MAX_BLOCKS} blocks."
        )
    return block_size


def plan_blocks(total_size: int, block_size: int | None = None) -> BlockPlan:
    """Build the block plan for an object of ``total_size`` bytes.

    Raises:
        ValueError: if ``total_size`` is negative, ``block_size`` is out of range, or the
            object cannot be represented within the block-count limit.
    """
    if total_size < 0:
        raise ValueError("total_size must be non-negative")

    if block_size is None:
        block_size = choose_block_size(total_size)
    elif not (1 <= block_size <= MAX_BLOCK_SIZE):
        raise ValueError(f"block_size must be between 1 and {MAX_BLOCK_SIZE} bytes")

    if total_size == 0:
        return BlockPlan(block_size=block_size, total_size=0, blocks=())

    count = math.ceil(total_size / block_size)
    if count > MAX_BLOCKS:
        raise ValueError(
            f"block_size {block_size} yields {count} blocks, over the {MAX_BLOCKS} limit"
        )

    blocks = tuple(
        Block(index=i, offset=i * block_size, length=min(block_size, total_size - i * block_size))
        for i in range(count)
    )
    return BlockPlan(block_size=block_size, total_size=total_size, blocks=blocks)
