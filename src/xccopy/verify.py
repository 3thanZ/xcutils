"""Integrity verification of a completed transfer (FR-013, SC-005)."""

from __future__ import annotations

from xccopy.providers.base import CommitResult, ObjectStat


class IntegrityError(RuntimeError):
    """Raised when the destination does not match the source after transfer."""


def verify(stat: ObjectStat, result: CommitResult) -> None:
    """Verify the destination against the source.

    Always checks byte size. When both sides report a hash of the same algorithm,
    compares those too. (Per-block checks are enforced server-side during staging.)
    """
    if result.size != stat.size:
        raise IntegrityError(
            f"size mismatch: source {stat.size} bytes, destination {result.size} bytes"
        )

    if stat.source_hash and result.dest_hash:
        src_algo, _, src_val = stat.source_hash.partition(":")
        dst_algo, _, dst_val = result.dest_hash.partition(":")
        if src_algo == dst_algo and src_val != dst_val:
            raise IntegrityError(
                f"{src_algo} mismatch: source {src_val}, destination {dst_val}"
            )
