import base64

from xccopy.providers.azure import block_id


def test_block_ids_are_equal_length() -> None:
    ids = [block_id(i) for i in (0, 1, 42, 99999)]
    assert len({len(i) for i in ids}) == 1, "Azure requires all block ids to be equal length"


def test_block_ids_are_unique_and_decodable() -> None:
    ids = [block_id(i) for i in range(100)]
    assert len(set(ids)) == 100
    assert base64.b64decode(ids[7]).startswith(b"xccopy-")
