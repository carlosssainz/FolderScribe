from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.hashing import ContentHash, DuplicateGroup, HashStatus


class TestDuplicateGroup:
    def test_group_creation(self) -> None:
        g = DuplicateGroup(
            group_id="abc123",
            hash_sha256="abcdef",
            file_size=100,
            file_count=3,
            wasted_space=200,
            file_paths=(Path("/a.txt"), Path("/b.txt"), Path("/c.txt")),
        )
        assert g.group_id == "abc123"
        assert g.hash_sha256 == "abcdef"
        assert g.file_size == 100
        assert g.file_count == 3
        assert g.wasted_space == 200
        assert len(g.file_paths) == 3

    def test_single_file_not_duplicate(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash1", 100),
            ]
        )
        assert len(groups) == 0

    def test_two_identical_files(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash_same", 100),
                _make_hash(Path("/b.txt"), "hash_same", 100),
            ]
        )
        assert len(groups) == 1
        g = groups[0]
        assert g.file_count == 2
        assert g.wasted_space == 100

    def test_three_identical_files(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash_x", 200),
                _make_hash(Path("/b.txt"), "hash_x", 200),
                _make_hash(Path("/c.txt"), "hash_x", 200),
            ]
        )
        assert len(groups) == 1
        g = groups[0]
        assert g.file_count == 3
        assert g.wasted_space == 400  # (3-1) * 200

    def test_two_separate_duplicate_groups(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash1", 100),
                _make_hash(Path("/b.txt"), "hash1", 100),
                _make_hash(Path("/c.txt"), "hash2", 200),
                _make_hash(Path("/d.txt"), "hash2", 200),
            ]
        )
        assert len(groups) == 2
        sizes = {g.file_size for g in groups}
        assert sizes == {100, 200}

    def test_same_hash_different_size_not_duplicate(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash_same", 100),
                _make_hash(Path("/b.txt"), "hash_same", 200),
            ]
        )
        assert len(groups) == 0

    def test_missing_hash_not_included(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash1", 100),
                _make_hash(Path("/b.txt"), "hash1", 100),
                ContentHash(
                    absolute_path=Path("/c.txt"),
                    algorithm="sha-256",
                    hash_sha256=None,
                    file_size=100,
                    file_modified_at=datetime.now(timezone.utc),
                    status=HashStatus.ERROR,
                ),
            ]
        )
        assert len(groups) == 1
        assert groups[0].file_count == 2

    def test_duplicate_group_ordering_by_wasted_space(self) -> None:
        groups = _find_duplicates(
            [
                _make_hash(Path("/a.txt"), "hash_small", 50),
                _make_hash(Path("/b.txt"), "hash_small", 50),
                _make_hash(Path("/c.txt"), "hash_large", 500),
                _make_hash(Path("/d.txt"), "hash_large", 500),
                _make_hash(Path("/e.txt"), "hash_large", 500),
            ]
        )
        # Largest wasted space first: 500*2=1000 for group of 3, then 50 for group of 2
        assert groups[0].wasted_space >= groups[1].wasted_space


def _make_hash(path: Path, hash_hex: str, size: int) -> ContentHash:
    return ContentHash(
        absolute_path=path,
        algorithm="sha-256",
        hash_sha256=hash_hex,
        file_size=size,
        file_modified_at=datetime.now(timezone.utc),
        status=HashStatus.COMPUTED,
        computed_at=datetime.now(timezone.utc),
    )


def _find_duplicates(hashes: list[ContentHash]) -> list[DuplicateGroup]:
    from collections import defaultdict

    groups_map: dict[tuple[str, int], list[Path]] = defaultdict(list)
    for h in hashes:
        if h.hash_sha256 is not None and h.status in (  # noqa: E501
            HashStatus.COMPUTED, HashStatus.REUSED
        ):
            groups_map[(h.hash_sha256, h.file_size)].append(h.absolute_path)

    result = []
    for (hash_hex, size), paths in groups_map.items():
        if len(paths) > 1:
            result.append(
                DuplicateGroup(
                    group_id=hash_hex[:16],
                    hash_sha256=hash_hex,
                    file_size=size,
                    file_count=len(paths),
                    wasted_space=(len(paths) - 1) * size,
                    file_paths=tuple(sorted(paths)),
                )
            )
    result.sort(key=lambda g: g.wasted_space, reverse=True)
    return result
