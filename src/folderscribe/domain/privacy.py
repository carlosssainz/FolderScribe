from enum import Enum


class PrivacyLevel(Enum):
    EXCLUDE = "exclude"
    METADATA_ONLY = "metadata_only"
    LOCAL = "local"
    FULL = "full"

    @property
    def allows_text_extraction(self) -> bool:
        return self in (PrivacyLevel.LOCAL, PrivacyLevel.FULL)

    @property
    def allows_file_open(self) -> bool:
        return self in (
            PrivacyLevel.LOCAL,
            PrivacyLevel.FULL,
            PrivacyLevel.METADATA_ONLY,
        )

    @property
    def allows_external_send(self) -> bool:
        return self == PrivacyLevel.FULL
