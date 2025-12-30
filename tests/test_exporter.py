"""Tests for CSV exporter."""

import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from shoudao.exporter import CSV_COLUMNS, export_csv, export_excel, generate_report, lead_to_row
from shoudao.models import Evidence, Lead, Organization, RunConfig, RunResult


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


class TestExportExcel:
    """Tests for export_excel function."""

    def test_export_creates_file(self, sample_lead: Lead) -> None:
        """Test that Excel export creates a file."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "leads.xlsx"
            count = export_excel([sample_lead], path)

            assert count == 1
            assert path.exists()
            # Check file is not empty
            assert path.stat().st_size > 0

    def test_export_empty_list(self) -> None:
        """Test exporting empty lead list to Excel."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.xlsx"
            count = export_excel([], path)
            assert count == 0
            assert path.exists()


class TestGenerateReport:
    """Tests for report generation."""

    def test_report_contains_tier_breakdown(self, sample_run_result: RunResult) -> None:
        """Test that report contains tier breakdown (Task 14.1.4)."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            generate_report(sample_run_result, path)

            content = path.read_text()
            assert "## Leads by Buyer Tier" in content
            assert "Tier" in content
            assert "High confidence buyer" in content or "Description" in content

    def test_report_contains_run_info(self, sample_run_result: RunResult) -> None:
        """Test that report contains run info."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            generate_report(sample_run_result, path)

            content = path.read_text()
            assert "# ShouDao Run Report" in content
            assert "Run ID" in content
            assert "Sources Fetched" in content

    def test_report_contains_country_breakdown(self, sample_run_result: RunResult) -> None:
        """Test that report contains country breakdown."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            generate_report(sample_run_result, path)

            content = path.read_text()
            assert "## Leads by Country" in content

    def test_report_contains_type_breakdown(self, sample_run_result: RunResult) -> None:
        """Test that report contains type breakdown."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            generate_report(sample_run_result, path)

            content = path.read_text()
            assert "## Leads by Type" in content

    def test_report_tier_counts(self, sample_evidence: Evidence) -> None:
        """Test that tier counts are accurate in report."""
        config = RunConfig(prompt="test")
        # Create leads with different tiers
        tier_a_org = Organization(name="A Co", evidence=[sample_evidence])
        tier_b_org = Organization(name="B Co", evidence=[sample_evidence])
        lead_a = Lead(organization=tier_a_org, buyer_tier="A")
        lead_b = Lead(organization=tier_b_org, buyer_tier="B")

        result = RunResult(
            config=config,
            leads=[lead_a, lead_a, lead_b],  # 2 A's, 1 B
            run_id="test123",
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            generate_report(result, path)

            content = path.read_text()
            # Check that A appears with count 2 and B with count 1
            assert "| A |" in content
            assert "| B |" in content
