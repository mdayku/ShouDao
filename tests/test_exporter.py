"""Tests for CSV exporter."""

import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from shoudao.exporter import CSV_COLUMNS, export_csv, lead_to_row
from shoudao.models import Lead


class TestLeadToRow:
    """Tests for lead_to_row function."""

    def test_lead_to_row_basic(self, sample_lead: Lead) -> None:
        """Test converting a lead to a CSV row."""
        row = lead_to_row(sample_lead)

        assert row["organization_name"] == "Acme Corp"
        assert row["org_type"] == "contractor"
        assert row["country"] == "USA"
        assert row["email"] == "info@example.com"
        assert row["contact_name"] == "John Smith"
        assert row["confidence"] == "0.80"

    def test_lead_to_row_all_columns(self, sample_lead: Lead) -> None:
        """Test that all CSV columns are present."""
        row = lead_to_row(sample_lead)

        for col in CSV_COLUMNS:
            assert col in row, f"Missing column: {col}"


class TestExportCsv:
    """Tests for export_csv function."""

    def test_export_to_stringio(self, sample_lead: Lead) -> None:
        """Test exporting to a StringIO object."""
        output = io.StringIO()
        count = export_csv([sample_lead], output)

        assert count == 1
        output.seek(0)
        reader = csv.DictReader(output)
        rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["organization_name"] == "Acme Corp"

    def test_export_to_file(self, sample_lead: Lead) -> None:
        """Test exporting to a file."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "leads.csv"
            count = export_csv([sample_lead], path)

            assert count == 1
            assert path.exists()

            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1

    def test_export_empty_list(self) -> None:
        """Test exporting empty lead list."""
        output = io.StringIO()
        count = export_csv([], output)

        assert count == 0
        output.seek(0)
        reader = csv.DictReader(output)
        rows = list(reader)

        assert len(rows) == 0

    def test_export_multiple_leads(self, sample_lead: Lead) -> None:
        """Test exporting multiple leads."""
        output = io.StringIO()
        count = export_csv([sample_lead, sample_lead], output)

        assert count == 2
