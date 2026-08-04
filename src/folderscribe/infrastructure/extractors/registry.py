from pathlib import Path

from folderscribe.domain.interfaces import TextExtractor


class TextExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: list[TextExtractor] = []

    def register(self, extractor: TextExtractor) -> None:
        self._extractors.append(extractor)

    def get_extractor(self, path: Path) -> TextExtractor | None:
        for extractor in self._extractors:
            if extractor.supports(path):
                return extractor
        return None

    @property
    def extractors(self) -> tuple[TextExtractor, ...]:
        return tuple(self._extractors)
