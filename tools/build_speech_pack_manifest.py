#!/usr/bin/env python3
"""Build and check an expanded immutable AI Guardians speech-pack manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

SCHEMA = 1
PAYLOAD_SCHEMA = 1
PAYLOAD_ALGORITHM = "sha256-path-size-content-v1"
MAX_MEMBER_BYTES = 64 * 1024 * 1024
CODEC = {
    "audio": "Opus",
    "channels": 1,
    "container": "Ogg",
    "sample_rate_hz": 24000,
    "target_bitrate_kbps": 48,
}


class ManifestError(ValueError):
    """Raised when an input cannot describe an immutable speech pack."""


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"cannot read JSON input {path}: {error}") from error
    if not isinstance(value, dict):
        raise ManifestError(f"JSON input must be an object: {path}")
    return value


def _hash_regular_file(path: Path) -> tuple[int, str]:
    """Hash one unchanged ordinary file without following a final symlink."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ManifestError(f"payload member is not an ordinary file: {path}")
    if before.st_size > MAX_MEMBER_BYTES:
        raise ManifestError(
            f"payload member exceeds {MAX_MEMBER_BYTES} bytes: {path}"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ManifestError(f"cannot open payload member {path}: {error}") from error

    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ManifestError(f"payload member is not an ordinary file: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_MEMBER_BYTES:
                raise ManifestError(
                    f"payload member exceeds {MAX_MEMBER_BYTES} bytes: {path}"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_opened = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_opened or identity_opened != identity_after:
        raise ManifestError(f"payload member changed while hashing: {path}")
    if size != before.st_size:
        raise ManifestError(f"payload member size changed while hashing: {path}")
    return size, digest.hexdigest()


def inventory_lines(lines_dir: Path) -> tuple[list[dict[str, object]], int, str]:
    """Inventory a flat, link-free directory of Opus payload members."""
    try:
        supplied_root = lines_dir.lstat()
    except OSError as error:
        raise ManifestError(f"cannot inspect lines directory {lines_dir}: {error}") from error
    if stat.S_ISLNK(supplied_root.st_mode):
        raise ManifestError(f"lines directory link is forbidden: {lines_dir}")
    root = lines_dir.resolve(strict=True)
    if not root.is_dir():
        raise ManifestError(f"lines path is not a directory: {lines_dir}")

    entries = sorted(root.iterdir(), key=lambda path: path.name)
    files: list[dict[str, object]] = []
    contract = hashlib.sha256()
    total_bytes = 0
    for path in entries:
        if path.is_symlink():
            raise ManifestError(f"payload link is forbidden: {path}")
        if path.name.startswith(".") or path.suffix != ".opus":
            raise ManifestError(f"unexpected payload entry: {path}")
        size, sha256 = _hash_regular_file(path)
        record = {"bytes": size, "name": path.name, "sha256": sha256}
        files.append(record)
        contract.update(path.name.encode("utf-8"))
        contract.update(b"\0")
        contract.update(str(size).encode("ascii"))
        contract.update(b"\0")
        contract.update(sha256.encode("ascii"))
        contract.update(b"\n")
        total_bytes += size

    if not files:
        raise ManifestError(f"lines directory is empty: {lines_dir}")
    return files, total_bytes, contract.hexdigest()


def build_manifest(
    lines_dir: Path,
    compact_manifest_path: Path,
    version: str,
    candidate_sha: str,
    source_manifest_label: str,
) -> dict[str, object]:
    compact = _load_json(compact_manifest_path)
    expected_compact = {
        "schema_version": PAYLOAD_SCHEMA,
        "algorithm": PAYLOAD_ALGORITHM,
    }
    for field, expected in expected_compact.items():
        if compact.get(field) != expected:
            raise ManifestError(
                f"compact manifest {field} must be {expected!r}, got {compact.get(field)!r}"
            )
    if not version or "/" in version or "\\" in version:
        raise ManifestError(f"invalid immutable version label: {version!r}")
    if len(candidate_sha) != 40 or any(c not in "0123456789abcdef" for c in candidate_sha):
        raise ManifestError("candidate SHA must be 40 lowercase hexadecimal characters")
    source_sha = compact.get("source_manifest_sha256")
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 64
        or any(c not in "0123456789abcdef" for c in source_sha)
    ):
        raise ManifestError("compact manifest has no valid source_manifest_sha256")

    files, total_bytes, contract_sha256 = inventory_lines(lines_dir)
    observed = {
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_sha256": contract_sha256,
    }
    for field, value in observed.items():
        if compact.get(field) != value:
            raise ManifestError(
                f"payload does not match compact manifest {field}: "
                f"expected {compact.get(field)!r}, observed {value!r}"
            )

    return {
        "candidate_sha": candidate_sha,
        "codec": CODEC,
        "files": files,
        "files_contract_sha256": contract_sha256,
        "immutable": True,
        "line_count": len(files),
        "schema": SCHEMA,
        "source_manifest": source_manifest_label,
        "source_manifest_sha256": source_sha,
        "total_bytes": total_bytes,
        "version": version,
    }


def canonical_json(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines-dir", type=Path, required=True)
    parser.add_argument("--compact-manifest", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--source-manifest-label", default="tools/voice/manifest.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that OUTPUT already equals the deterministic result",
    )
    args = parser.parse_args(argv)

    try:
        payload = build_manifest(
            args.lines_dir,
            args.compact_manifest,
            args.version,
            args.candidate_sha,
            args.source_manifest_label,
        )
        content = canonical_json(payload)
        if args.check:
            try:
                current = args.output.read_bytes()
            except OSError as error:
                raise ManifestError(f"cannot read output {args.output}: {error}") from error
            if current != content:
                raise ManifestError(f"manifest is stale or noncanonical: {args.output}")
            action = "verified"
        else:
            atomic_write(args.output, content)
            action = "written"
    except (ManifestError, OSError) as error:
        parser.error(str(error))

    print(
        f"Speech-pack manifest {action}: {payload['line_count']} files, "
        f"{payload['total_bytes']} bytes, {payload['files_contract_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
