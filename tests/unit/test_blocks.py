import math

import pytest

from xccopy.blocks import (
    DEFAULT_BLOCK_SIZE,
    MAX_BLOCK_SIZE,
    MAX_BLOCKS,
    choose_block_size,
    plan_blocks,
)


def test_zero_byte_object_has_no_blocks() -> None:
    plan = plan_blocks(0)
    assert plan.count == 0
    assert plan.total_size == 0


def test_block_offsets_and_last_block_length() -> None:
    plan = plan_blocks(2500, block_size=1000)
    assert plan.count == 3
    assert [b.offset for b in plan.blocks] == [0, 1000, 2000]
    assert [b.length for b in plan.blocks] == [1000, 1000, 500]
    assert sum(b.length for b in plan.blocks) == 2500


def test_adaptive_block_size_keeps_within_block_limit() -> None:
    huge = DEFAULT_BLOCK_SIZE * (MAX_BLOCKS + 100)  # would exceed the cap at default size
    block_size = choose_block_size(huge)
    assert block_size > DEFAULT_BLOCK_SIZE
    assert math.ceil(huge / block_size) <= MAX_BLOCKS


def test_small_object_uses_default_block_size() -> None:
    assert choose_block_size(1234) == DEFAULT_BLOCK_SIZE


def test_object_too_large_to_represent() -> None:
    too_big = MAX_BLOCK_SIZE * MAX_BLOCKS + 1
    with pytest.raises(ValueError):
        plan_blocks(too_big)


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        plan_blocks(-1)
    with pytest.raises(ValueError):
        plan_blocks(100, block_size=0)
