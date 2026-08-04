from dataclasses import dataclass

from folderscribe.domain.ocr import OcrMode


@dataclass(frozen=True)
class ExtractionConfig:
    max_stored_chars: int = 100000
    max_read_bytes: int = 10_485_760
    max_pdf_pages: int = 500
    gui_preview_chars: int = 5000
    ocr_heuristic_version: str = "1"
    ocr_lang: str = "eng"
    ocr_dpi_fast: int = 150
    ocr_dpi_full: int = 300
    ocr_psm_fast: int = 3
    ocr_psm_full: int = 6

    @property
    def config_version(self) -> str:
        return (
            f"chars={self.max_stored_chars}"
            f"|read={self.max_read_bytes}"
            f"|pages={self.max_pdf_pages}"
            f"|ocr_heur={self.ocr_heuristic_version}"
        )

    def ocr_config_version(self, mode: OcrMode) -> str:
        return (
            f"ocr_mode={mode.value}"
            f"|dpi_fast={self.ocr_dpi_fast}"
            f"|dpi_full={self.ocr_dpi_full}"
            f"|psm_fast={self.ocr_psm_fast}"
            f"|psm_full={self.ocr_psm_full}"
            f"|lang={self.ocr_lang}"
        )
