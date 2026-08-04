from folderscribe.infrastructure.needs_ocr import assess_needs_ocr


class TestOcrHeuristic:
    def test_no_pages_no_ocr(self) -> None:
        needs, reason = assess_needs_ocr(0, 0, 0, 0)
        assert not needs
        assert reason is None

    def test_no_processed_pages(self) -> None:
        needs, reason = assess_needs_ocr(5, 0, 0, 0)
        assert not needs

    def test_no_text_at_all(self) -> None:
        needs, reason = assess_needs_ocr(3, 3, 0, 0)
        assert needs
        assert reason == "no_extractable_text"

    def test_some_text_some_pages(self) -> None:
        needs, _ = assess_needs_ocr(5, 5, 1000, 5)
        assert not needs

    def test_very_little_text(self) -> None:
        needs, reason = assess_needs_ocr(10, 10, 5, 1)
        assert needs
        assert reason == "insufficient_text"

    def test_text_in_few_pages(self) -> None:
        needs, reason = assess_needs_ocr(20, 20, 200, 1)
        assert needs
        assert reason == "text_in_too_few_pages"

    def test_not_truncated(self) -> None:
        needs, _ = assess_needs_ocr(5, 5, 100, 5, is_truncated=True)
        assert not needs

    def test_encrypted(self) -> None:
        needs, _ = assess_needs_ocr(5, 5, 0, 0, is_encrypted=True)
        assert not needs

    def test_single_page_no_text(self) -> None:
        needs, reason = assess_needs_ocr(1, 1, 0, 0)
        assert needs
        assert reason == "no_extractable_text"

    def test_get_version(self) -> None:
        from folderscribe.infrastructure.needs_ocr import get_ocr_heuristic_version

        assert get_ocr_heuristic_version() == "1"
