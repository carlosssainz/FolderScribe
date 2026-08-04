from collections.abc import Callable

from folderscribe.domain.hashing import ContentHash, HashResult, HashStatus
from folderscribe.domain.interfaces import ContentHasher, ScanSessionRepository


class ComputeHashesUseCase:
    def __init__(
        self,
        hasher: ContentHasher,
        repository: ScanSessionRepository,
    ) -> None:
        self._hasher = hasher
        self._repository = repository

    def execute(
        self,
        session_id: str,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> HashResult:
        entries = self._repository.get_entries_for_session(session_id)

        file_entries = [
            e for e in entries
            if e.element_type == "file" and e.status == "indexed"
        ]

        total = len(file_entries)
        results: list[ContentHash] = []
        computed_count = 0
        reused_count = 0
        skipped_count = 0
        modified_count = 0
        error_count = 0

        for idx, entry in enumerate(file_entries):
            if cancel_check is not None and cancel_check():
                break

            path = entry.absolute_path

            if entry.size is None or entry.modified_at is None:
                results.append(
                    ContentHash(
                        absolute_path=path,
                        algorithm="sha-256",
                        hash_sha256=None,
                        file_size=0,
                        file_modified_at=entry.modified_at,
                        status=HashStatus.SKIPPED,
                        error_message="Missing size or modification time",
                    )
                )
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped (no metadata)")
                continue

            reusable = self._repository.find_reusable_hash(
                path, entry.size, entry.modified_at
            )

            if reusable is not None:
                results.append(reusable)
                reused_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Reused")
                continue

            content_hash = self._hasher.compute_hash(path)

            status = content_hash.status
            if status == HashStatus.COMPUTED:
                computed_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Computed")
            elif status == HashStatus.ERROR:
                error_count += 1
                if progress_callback is not None:
                    msg = content_hash.error_message or "unknown"
                    progress_callback(idx + 1, total, f"Error: {msg}")
            elif status == HashStatus.MODIFIED_DURING_READ:
                modified_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Modified during read")
            elif status == HashStatus.SKIPPED:
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped")
            else:
                if progress_callback is not None:
                    progress_callback(idx + 1, total, f"Status: {status.value}")

            results.append(content_hash)

        self._repository.save_content_hashes(session_id, results)

        duplicate_groups = self._repository.find_duplicates(session_id)

        return HashResult(
            session_id=session_id,
            hashes=tuple(results),
            total_processed=len(results),
            computed_count=computed_count,
            reused_count=reused_count,
            skipped_count=skipped_count,
            modified_count=modified_count,
            error_count=error_count,
            duplicate_groups=duplicate_groups,
        )
