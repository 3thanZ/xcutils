import pytest

from xcutils_common.uri import parse_blob_uri


def test_parse_gcs() -> None:
    loc = parse_blob_uri("gs://my-bucket/path/to/object.txt")
    assert loc.scheme == "gs"
    assert loc.bucket == "my-bucket"
    assert loc.key == "path/to/object.txt"
    assert loc.container is None
    assert loc.uri == "gs://my-bucket/path/to/object.txt"


def test_parse_azure() -> None:
    loc = parse_blob_uri("az://myaccount/mycontainer/path/to/blob.bin")
    assert loc.scheme == "az"
    assert loc.bucket == "myaccount"
    assert loc.container == "mycontainer"
    assert loc.key == "path/to/blob.bin"
    assert loc.uri == "az://myaccount/mycontainer/path/to/blob.bin"


def test_parse_s3_reserved() -> None:
    loc = parse_blob_uri("s3://bucket/key")
    assert loc.scheme == "s3"
    assert loc.bucket == "bucket"
    assert loc.key == "key"


@pytest.mark.parametrize(
    "bad",
    [
        "no-scheme/path",
        "ftp://host/path",
        "gs://bucket-only",
        "az://account/container-only",
    ],
)
def test_invalid_uris_raise(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_blob_uri(bad)
