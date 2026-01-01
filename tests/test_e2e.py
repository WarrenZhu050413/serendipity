"""End-to-end integration tests.

These tests run real API calls and are slow. They are skipped by default.

Run with: pytest -m e2e
"""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from serendipity.cli import app
from serendipity.storage import StorageManager

runner = CliRunner()


@pytest.mark.e2e
class TestEndToEnd:
    """Real end-to-end tests that hit actual APIs."""

    @pytest.fixture
    def temp_storage_with_profile(self):
        """Create a temporary storage with a real taste profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            storage.save_taste(
                "I enjoy science fiction, jazz music, and programming. "
                "I like thoughtful content that makes unexpected connections."
            )
            yield storage, Path(tmpdir)

    def test_discover_json_output(self, temp_storage_with_profile):
        """Test full discover flow with JSON output.

        This test:
        - Runs actual Claude API call
        - Parses real response
        - Outputs JSON to stdout

        Takes ~30-60 seconds depending on API response time.
        """
        import json
        import os

        storage, tmpdir = temp_storage_with_profile

        # Set storage path via environment
        env = os.environ.copy()
        env["SERENDIPITY_BASE_DIR"] = str(tmpdir)

        result = runner.invoke(
            app,
            [
                "discover",
                "I'm curious about the intersection of music and mathematics",
                "-o", "json",
                "--dest", "stdout",
                "-n", "2",  # Only 2 recommendations for speed
            ],
            env=env,
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Output should contain valid JSON
        # Find the JSON in the output (may have other text before/after)
        stdout = result.stdout
        json_start = stdout.find("{")
        json_end = stdout.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = stdout[json_start:json_end]
            data = json.loads(json_str)

            # Should have recommendations
            assert "convergent" in data or "divergent" in data
            all_recs = data.get("convergent", []) + data.get("divergent", [])
            assert len(all_recs) > 0, "Expected at least one recommendation"

            # Each recommendation should have required fields
            for rec in all_recs:
                assert "url" in rec, f"Missing url in {rec}"
                assert "reason" in rec, f"Missing reason in {rec}"

    def test_discover_markdown_output(self, temp_storage_with_profile):
        """Test full discover flow with markdown output."""
        import os

        storage, tmpdir = temp_storage_with_profile

        env = os.environ.copy()
        env["SERENDIPITY_BASE_DIR"] = str(tmpdir)

        result = runner.invoke(
            app,
            [
                "discover",
                "Recommend something unexpected",
                "-o", "markdown",
                "--dest", "stdout",
                "-n", "2",
            ],
            env=env,
        )

        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Should contain markdown formatting
        assert "##" in result.stdout or "**" in result.stdout
        # Should contain at least one URL
        assert "http" in result.stdout
