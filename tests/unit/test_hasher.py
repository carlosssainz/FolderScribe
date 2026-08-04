import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from folderscribe.domain.hashing import HashStatus
from folderscribe.infrastructure.hasher import StreamingHasher


@pytest.fixture
def hasher() -> StreamingHasher:
    return StreamingHasher()


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestStreamingHasher:
    def test_computes_correct_hash(  # noqa: E501
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "test.txt"
        content = b"Hello, FolderScribe!"
        f.write_bytes(content)
        result = hasher.compute_hash(f)
        assert result.status == HashStatus.COMPUTED
        assert result.hash_sha256 == _sha256_of(content)
        assert result.algorithm == "sha-256"
        assert result.file_size == len(content)
        assert result.error_message is None

    def test_empty_file(self, tmp_path: Path, hasher: StreamingHasher) -> None:
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = hasher.compute_hash(f)
        assert result.status == HashStatus.COMPUTED
        assert result.hash_sha256 == _sha256_of(b"")
        assert result.file_size == 0

    def test_large_file_streaming(  # noqa: E501
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "large.bin"
        content = b"X" * (1024 * 1024)  # 1 MB, multiple 64KB blocks
        f.write_bytes(content)
        result = hasher.compute_hash(f)
        assert result.status == HashStatus.COMPUTED
        assert result.hash_sha256 == _sha256_of(content)
        assert result.file_size == len(content)

    def test_identical_content_same_hash(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        content = b"identical content"
        f1.write_bytes(content)
        f2.write_bytes(content)
        r1 = hasher.compute_hash(f1)
        r2 = hasher.compute_hash(f2)
        assert r1.hash_sha256 == r2.hash_sha256
        assert r1.status == HashStatus.COMPUTED
        assert r2.status == HashStatus.COMPUTED

    def test_different_content_different_hash(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        r1 = hasher.compute_hash(f1)
        r2 = hasher.compute_hash(f2)
        assert r1.hash_sha256 != r2.hash_sha256
        assert r1.file_size == r2.file_size

    def test_symlink_skipped(self, tmp_path: Path, hasher: StreamingHasher) -> None:
        target = tmp_path / "real.txt"
        target.write_bytes(b"real content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        result = hasher.compute_hash(link)
        assert result.status == HashStatus.SKIPPED
        assert result.error_message == "Symbolic link"

    def test_nonexistent_file_errors(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "nonexistent.txt"
        result = hasher.compute_hash(f)
        assert result.status == HashStatus.ERROR
        assert result.hash_sha256 is None

    def test_file_disappears_during_read(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "disappear.txt"
        f.write_bytes(b"content")

        original_open = open

        def _disappearing_open(*args, **kwargs):  # type: ignore[no-untyped-def]
            f.unlink()
            return original_open(*args, **kwargs)

        with patch("builtins.open", _disappearing_open):
            result = hasher.compute_hash(f)

        assert result.status == HashStatus.ERROR
        assert result.hash_sha256 is None

    def test_permission_error(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "restricted.txt"
        f.write_bytes(b"secret")
        f.chmod(0o000)

        try:
            result = hasher.compute_hash(f)
            assert result.status == HashStatus.ERROR
            assert "Permission denied" in (result.error_message or "")
        finally:
            f.chmod(0o644)

    def test_hash_and_status_fields(
        self, tmp_path: Path, hasher: StreamingHasher
    ) -> None:
        f = tmp_path / "data.bin"
        content = b"test data"
        f.write_bytes(content)
        result = hasher.compute_hash(f)
        assert result.absolute_path == f
        assert result.file_size == len(content)
        assert result.computed_at is not None
        assert result.error_message is None
