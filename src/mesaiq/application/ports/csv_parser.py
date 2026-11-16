"""CSV review parser contract."""

from typing import Protocol

from mesaiq.application.dtos.import_reviews import RawReviewRow


class CsvReviewParser(Protocol):
    """Port for parsing raw CSV bytes into structural review rows."""

    def parse(self, content: bytes) -> list[RawReviewRow]:
        """Parse CSV bytes into raw row records with line numbers.

        Raises:
            ValueError: If the CSV is empty, malformed, or missing required columns.
        """
        ...
