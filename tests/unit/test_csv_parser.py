"""Unit tests for the CSV review parser implementation."""

import pytest

from mesaiq.infrastructure.parsers.csv_review_parser import CsvReviewParserImpl


class TestCsvReviewParser:
    def setup_method(self) -> None:
        self.parser = CsvReviewParserImpl()

    def test_parse_valid_csv(self) -> None:
        content = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Comida deliciosa!,2026-10-12T14:30:00\n"
            b"ifood,rev-002,2,Pedido demorou.,2026-10-13T19:15:00\n"
        )
        rows = self.parser.parse(content)
        assert len(rows) == 2

        assert rows[0].line_number == 2
        assert rows[0].data["source_system"] == "google"
        assert rows[0].data["external_id"] == "rev-001"
        assert rows[0].data["rating"] == "5"
        assert rows[0].data["content"] == "Comida deliciosa!"
        assert rows[0].data["reviewed_at"] == "2026-10-12T14:30:00"

        assert rows[1].line_number == 3
        assert rows[1].data["source_system"] == "ifood"
        assert rows[1].data["external_id"] == "rev-002"
        assert rows[1].data["rating"] == "2"

    def test_parse_utf8_with_bom(self) -> None:
        content = (
            b"\xef\xbb\xbfsource_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Excelente,2026-10-12T14:30:00\n"
        )
        rows = self.parser.parse(content)
        assert len(rows) == 1
        assert rows[0].data["source_system"] == "google"

    def test_parse_with_commas_in_quotes(self) -> None:
        content = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b'google,rev-001,4,"Ambiente agradavel, bom atendimento",2026-10-12T14:30:00\n'
        )
        rows = self.parser.parse(content)
        assert len(rows) == 1
        assert rows[0].data["content"] == "Ambiente agradavel, bom atendimento"

    def test_parse_with_newlines_in_quoted_content_preserves_start_lines(self) -> None:
        # Line 1: Header
        # Line 2-3: First record (occupies 2 lines: 2 and 3)
        # Line 4: Second record (must start at line 4)
        content = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b'google,rev-001,5,"Linha 1 do feedback\nLinha 2 do feedback",2026-10-12T14:30:00\n'
            b'ifood,rev-002,1,"Comida fria",2026-10-13T12:00:00\n'
        )
        rows = self.parser.parse(content)
        assert len(rows) == 2
        assert rows[0].line_number == 2
        assert "Linha 1 do feedback\nLinha 2 do feedback" in rows[0].data["content"]
        assert rows[1].line_number == 4

    def test_parse_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="CSV file is empty"):
            self.parser.parse(b"")

        with pytest.raises(ValueError, match="CSV file is empty"):
            self.parser.parse(b"   \n  \n")

    def test_parse_missing_required_columns_raises(self) -> None:
        content = b"source_system,external_id,content,reviewed_at\ngoogle,1,Texto,2026-10-10\n"
        with pytest.raises(ValueError, match=r"Missing required columns.*rating"):
            self.parser.parse(content)

    def test_parse_duplicate_header_columns_raises(self) -> None:
        content = (
            b"source_system,external_id,rating,content,reviewed_at,rating\n"
            b"google,1,5,Texto,2026-10-10,5\n"
        )
        with pytest.raises(ValueError, match="Duplicate columns in CSV header: rating"):
            self.parser.parse(content)

    def test_parse_incompatible_column_count_raises(self) -> None:
        content = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,1,5,Texto\n"  # 4 columns instead of 5
        )
        with pytest.raises(ValueError, match=r"Line 2 has 4 columns, expected 5"):
            self.parser.parse(content)

    def test_parse_unclosed_quotes_raises(self) -> None:
        content = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b'google,1,5,"Aspa nao fechada,2026-10-10\n'
        )
        with pytest.raises(ValueError, match="Structural CSV error"):
            self.parser.parse(content)

    def test_parse_invalid_encoding_raises(self) -> None:
        # Invalid UTF-8 sequence
        content = b"\xff\xfe\x00\x00source_system,external_id,rating,content,reviewed_at"
        with pytest.raises(ValueError, match="Invalid file encoding"):
            self.parser.parse(content)
