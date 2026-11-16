"""CSV review parser implementation using Python standard library csv module."""

import csv
import io

from mesaiq.application.dtos.import_reviews import RawReviewRow

REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "source_system",
        "external_id",
        "rating",
        "content",
        "reviewed_at",
    }
)


class CsvReviewParserImpl:
    """Parses raw CSV bytes into RawReviewRow records.

    Handles UTF-8, UTF-8-SIG (BOM), quotes, embedded commas, and escaped newlines.
    Does NOT enforce domain validation; extracts structural records.
    """

    def parse(self, content: bytes) -> list[RawReviewRow]:
        """Parse CSV bytes into raw rows with 1-based start line numbers.

        Raises:
            ValueError: If file is empty, encoding is invalid, header is malformed,
                        or columns are missing/duplicated/incompatible.
        """
        if not content or not content.strip():
            raise ValueError("CSV file is empty")

        # Decode using utf-8-sig to transparently strip BOM if present
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Invalid file encoding: must be valid UTF-8 ({exc})") from exc

        # Read into string stream with strict=True
        stream = io.StringIO(text, newline="")
        reader = csv.reader(stream, strict=True)

        # 1. Read header
        try:
            header_row = next(reader)
        except StopIteration as exc:
            raise ValueError("CSV file is empty or contains no rows") from exc
        except csv.Error as exc:
            raise ValueError(f"Structural CSV error in header: {exc}") from exc

        # Normalize header column names (stripped)
        header = [col.strip() for col in header_row]

        # Check for duplicate columns in header
        if len(header) != len(set(header)):
            # Find which column(s) were duplicated
            seen_cols: set[str] = set()
            dup_cols: list[str] = []
            for col in header:
                if col in seen_cols and col not in dup_cols:
                    dup_cols.append(col)
                seen_cols.add(col)
            raise ValueError(f"Duplicate columns in CSV header: {', '.join(dup_cols)}")

        # Check required columns
        missing_columns = REQUIRED_COLUMNS - set(header)
        if missing_columns:
            sorted_missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required columns in CSV header: {sorted_missing}")

        expected_column_count = len(header)
        col_to_idx = {col: idx for idx, col in enumerate(header)}

        # 2. Parse data rows tracking the starting physical line of each record
        results: list[RawReviewRow] = []

        while True:
            # Capture start line before reading the next record
            start_line = reader.line_num + 1

            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as exc:
                raise ValueError(f"Structural CSV error around line {start_line}: {exc}") from exc

            # Skip completely empty lines
            if not row or not any(field.strip() for field in row):
                continue

            # Validate column count matches header
            if len(row) != expected_column_count:
                raise ValueError(
                    f"Line {start_line} has {len(row)} columns, expected {expected_column_count}"
                )

            # Build dict for row based on columns in header
            row_dict: dict[str, str] = {}
            for col in REQUIRED_COLUMNS:
                idx = col_to_idx[col]
                row_dict[col] = row[idx]

            results.append(RawReviewRow(line_number=start_line, data=row_dict))

        return results
