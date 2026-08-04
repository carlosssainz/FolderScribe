import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.hashing import ContentHash, HashStatus
from folderscribe.domain.interfaces import ContentHasher

_BLOCK_SIZE = 65536


class StreamingHasher(ContentHasher):
    def compute_hash(self, path: Path) -> ContentHash:
        algorithm = "sha-256"

        if path.is_symlink():
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=0,
                file_modified_at=datetime.now(timezone.utc),
                status=HashStatus.SKIPPED,
                error_message="Symbolic link",
                computed_at=datetime.now(timezone.utc),
            )

        try:
            pre_stat = path.stat()
        except OSError as e:
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=0,
                file_modified_at=datetime.now(timezone.utc),
                status=HashStatus.ERROR,
                error_message=str(e),
                computed_at=datetime.now(timezone.utc),
            )

        if not os.path.isfile(path):
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=pre_stat.st_size,
                file_modified_at=datetime.fromtimestamp(
                    pre_stat.st_mtime, tz=timezone.utc
                ),
                status=HashStatus.SKIPPED,
                error_message="Not a regular file",
                computed_at=datetime.now(timezone.utc),
            )

        file_size = pre_stat.st_size
        modified_at = datetime.fromtimestamp(pre_stat.st_mtime, tz=timezone.utc)

        try:
            sha = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    block = f.read(_BLOCK_SIZE)
                    if not block:
                        break
                    sha.update(block)
            hash_hex = sha.hexdigest()
        except PermissionError:
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=file_size,
                file_modified_at=modified_at,
                status=HashStatus.ERROR,
                error_message="Permission denied",
                computed_at=datetime.now(timezone.utc),
            )
        except FileNotFoundError:
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=file_size,
                file_modified_at=modified_at,
                status=HashStatus.ERROR,
                error_message="File disappeared during read",
                computed_at=datetime.now(timezone.utc),
            )
        except OSError as e:
            error_msg = str(e) if str(e) else "Read error"
            status = HashStatus.ERROR
            if isinstance(e, PermissionError):
                error_msg = "Permission denied"
            elif isinstance(e, FileNotFoundError):
                error_msg = "File disappeared during read"
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=None,
                file_size=file_size,
                file_modified_at=modified_at,
                status=status,
                error_message=error_msg,
                computed_at=datetime.now(timezone.utc),
            )

        try:
            post_stat = path.stat()
        except OSError:
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=hash_hex,
                file_size=file_size,
                file_modified_at=modified_at,
                status=HashStatus.MODIFIED_DURING_READ,
                error_message="Could not verify stability after read",
                computed_at=datetime.now(timezone.utc),
            )

        post_size = post_stat.st_size
        post_mtime = datetime.fromtimestamp(post_stat.st_mtime, tz=timezone.utc)

        if post_size != file_size or post_mtime != modified_at:
            return ContentHash(
                absolute_path=path,
                algorithm=algorithm,
                hash_sha256=hash_hex,
                file_size=file_size,
                file_modified_at=modified_at,
                status=HashStatus.MODIFIED_DURING_READ,
                error_message="File size or modification time changed during read",
                computed_at=datetime.now(timezone.utc),
            )

        return ContentHash(
            absolute_path=path,
            algorithm=algorithm,
            hash_sha256=hash_hex,
            file_size=file_size,
            file_modified_at=modified_at,
            status=HashStatus.COMPUTED,
            computed_at=datetime.now(timezone.utc),
        )
