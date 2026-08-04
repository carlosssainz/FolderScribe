from pathlib import Path

from folderscribe.domain.privacy import PrivacyLevel


class TestPrivacyLevel:
    def test_exclude_no_extraction(self) -> None:
        assert not PrivacyLevel.EXCLUDE.allows_text_extraction
        assert not PrivacyLevel.EXCLUDE.allows_file_open

    def test_metadata_only_no_extraction(self) -> None:
        assert not PrivacyLevel.METADATA_ONLY.allows_text_extraction
        assert PrivacyLevel.METADATA_ONLY.allows_file_open

    def test_local_allows_extraction(self) -> None:
        assert PrivacyLevel.LOCAL.allows_text_extraction
        assert PrivacyLevel.LOCAL.allows_file_open
        assert not PrivacyLevel.LOCAL.allows_external_send

    def test_full_allows_all(self) -> None:
        assert PrivacyLevel.FULL.allows_text_extraction
        assert PrivacyLevel.FULL.allows_file_open
        assert PrivacyLevel.FULL.allows_external_send
