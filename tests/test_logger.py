"""Tests for the ProgressLogger class."""

from datetime import datetime

from shoudao.logger import ProgressLogger


class TestProgressLogger:
    """Tests for ProgressLogger."""

    def test_init(self) -> None:
        """Test logger initialization."""
        logger = ProgressLogger("test_run_123")
        assert logger.run_id == "test_run_123"
        assert logger.verbose is False
        assert isinstance(logger.start_time, datetime)

    def test_verbose_mode(self) -> None:
        """Test verbose mode initialization."""
        logger = ProgressLogger("test", verbose=True)
        assert logger.verbose is True

    def test_phase_logs_output(self, capsys) -> None:
        """Test that phase() produces output."""
        logger = ProgressLogger("test")
        logger.phase("Starting", "Step 1/6")
        captured = capsys.readouterr()
        assert "[Phase]" in captured.out
        assert "Starting" in captured.out
        assert "Step 1/6" in captured.out

    def test_progress_logs_output(self, capsys) -> None:
        """Test that progress() produces output."""
        logger = ProgressLogger("test")
        logger.progress("Query", 3, 10, "test query")
        captured = capsys.readouterr()
        assert "[Query 3/10]" in captured.out
        assert "test query" in captured.out

    def test_country_logs_output(self, capsys) -> None:
        """Test that country() produces output."""
        logger = ProgressLogger("test")
        logger.country("Jamaica", 1, 5, ["en"])
        captured = capsys.readouterr()
        assert "[Country 1/5]" in captured.out
        assert "Jamaica" in captured.out
        assert "en" in captured.out

    def test_query_logs_only_in_verbose(self, capsys) -> None:
        """Test that query() only logs in verbose mode."""
        logger = ProgressLogger("test", verbose=False)
        logger.query("test query", 1, 5, "en")
        captured = capsys.readouterr()
        assert captured.out == ""

        logger_verbose = ProgressLogger("test", verbose=True)
        logger_verbose.query("test query", 1, 5, "en")
        captured = capsys.readouterr()
        assert "[Query 1/5]" in captured.out

    def test_sources_logs_output(self, capsys) -> None:
        """Test that sources() produces output."""
        logger = ProgressLogger("test")
        logger.sources(10, 7, 3)
        captured = capsys.readouterr()
        assert "[SERP]" in captured.out
        assert "10 results" in captured.out
        assert "7 accepted" in captured.out

    def test_pages_logs_output(self, capsys) -> None:
        """Test that pages() produces output."""
        logger = ProgressLogger("test")
        logger.pages(5, 10)
        captured = capsys.readouterr()
        assert "[Pages]" in captured.out
        assert "5/10" in captured.out

    def test_extracted_logs_output(self, capsys) -> None:
        """Test that extracted() produces output."""
        logger = ProgressLogger("test")
        logger.extracted(10, 8, 2)
        captured = capsys.readouterr()
        assert "[Extracted]" in captured.out
        assert "10 companies" in captured.out
        assert "8 kept" in captured.out
        assert "2 dropped" in captured.out

    def test_deduped_logs_output(self, capsys) -> None:
        """Test that deduped() produces output."""
        logger = ProgressLogger("test")
        logger.deduped(100, 75)
        captured = capsys.readouterr()
        assert "[Deduped]" in captured.out
        assert "100 -> 75" in captured.out

    def test_tier_distribution_logs_output(self, capsys) -> None:
        """Test that tier_distribution() produces output."""
        logger = ProgressLogger("test")
        logger.tier_distribution({"A": 50, "B": 20, "C": 5, "excluded": 10})
        captured = capsys.readouterr()
        assert "[Tiers]" in captured.out
        assert "A=50" in captured.out

    def test_skip_logs_only_in_verbose(self, capsys) -> None:
        """Test that skip() only logs in verbose mode."""
        logger = ProgressLogger("test", verbose=False)
        logger.skip("Exporter", "China Trading Co")
        captured = capsys.readouterr()
        assert captured.out == ""

        logger_verbose = ProgressLogger("test", verbose=True)
        logger_verbose.skip("Exporter", "China Trading Co")
        captured = capsys.readouterr()
        assert "[Skip]" in captured.out

    def test_finish_logs_output(self, capsys) -> None:
        """Test that finish() produces output."""
        logger = ProgressLogger("test")
        logger.finish(100, "/path/to/output")
        captured = capsys.readouterr()
        assert "[ShouDao]" in captured.out
        assert "Run complete" in captured.out
        assert "100" in captured.out
        assert "/path/to/output" in captured.out

    def test_error_logs_to_stderr(self, capsys) -> None:
        """Test that error() logs to stderr."""
        logger = ProgressLogger("test")
        logger.error("Something went wrong")
        captured = capsys.readouterr()
        assert "[Error]" in captured.err
        assert "Something went wrong" in captured.err

    def test_warning_logs_to_stderr(self, capsys) -> None:
        """Test that warning() logs to stderr."""
        logger = ProgressLogger("test")
        logger.warning("This might be a problem")
        captured = capsys.readouterr()
        assert "[Warning]" in captured.err
        assert "This might be a problem" in captured.err

    def test_phase_tracking(self) -> None:
        """Test that phases are tracked with timestamps."""
        logger = ProgressLogger("test")
        logger.phase("Phase1")
        logger.phase("Phase2")
        assert "Phase1" in logger.phase_times
        assert "Phase2" in logger.phase_times
        assert logger.phase_times["Phase2"] >= logger.phase_times["Phase1"]

    def test_progress_percentage(self, capsys) -> None:
        """Test that progress shows percentage."""
        logger = ProgressLogger("test")
        logger.progress("Item", 5, 10)
        captured = capsys.readouterr()
        assert "50%" in captured.out

        logger.progress("Item", 3, 12)
        captured = capsys.readouterr()
        assert "25%" in captured.out
