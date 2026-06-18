import pytest
from typer.testing import CliRunner

from xccopy.cli import app

runner = CliRunner()


@pytest.mark.parametrize("value", ["0", "-1", "33", "100"])
def test_invalid_concurrency_rejected_before_io(value: str) -> None:
    result = runner.invoke(app, ["gs://b/src", "az://a/c/dst", "--concurrency", value])
    assert result.exit_code == 1
    assert "concurrency" in result.output.lower()


def test_invalid_block_size_rejected() -> None:
    result = runner.invoke(app, ["gs://b/src", "az://a/c/dst", "--block-size", "0"])
    assert result.exit_code == 1
    assert "block-size" in result.output.lower()
