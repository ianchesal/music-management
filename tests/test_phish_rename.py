import importlib.util
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-rename"
    loader = SourceFileLoader("phish_rename", str(path))
    spec = importlib.util.spec_from_loader("phish_rename", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = load_module()

FIXTURE_HTML_TWO_RESULTS = """
<html><body>
<a href="/LP-2259.html"><img alt="07/20/24 Xfinity Center, Mansfield, MA " title="..."></a>
<a href="/LP-2259.html">Phish</a>
<a href="/LP-2351.html"><img alt="07/20/24 Xfinity Center 4k, Mansfield 4k, MA " title="..."></a>
<a href="/LP-2351.html">Phish</a>
</body></html>
"""

FIXTURE_HTML_ONE_RESULT = """
<html><body>
<a href="/LP-515.html"><img alt="11/27/09 Times Union Center, Albany, NY " title="..."></a>
<a href="/LP-515.html">Phish</a>
</body></html>
"""

FIXTURE_HTML_NO_RESULTS = """
<html><body><p>No results found for your search.</p></body></html>
"""


class TestDateFromDirname:
    def test_yyyy_dash_mm_dd(self):
        assert pr.date_from_dirname("2024-07-20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_yyyy_underscore_mm_dd(self):
        assert pr.date_from_dirname("2024_07_20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_single_digit_month(self):
        assert pr.date_from_dirname("1994_6_19 Somewhere") == "1994-06-19"

    def test_single_digit_day(self):
        assert pr.date_from_dirname("1994-12-6 Goleta, CA") == "1994-12-06"

    def test_conforming_name_returns_none(self):
        assert pr.date_from_dirname("Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]") is None

    def test_undated_returns_none(self):
        assert pr.date_from_dirname("Live Bait Vol 10") is None


class TestIsConforming:
    def test_canonical_name_is_conforming(self):
        assert pr.is_conforming("Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]") is True

    def test_old_dash_format_is_not_conforming(self):
        assert pr.is_conforming("2024-07-20 Mansfield MA") is False

    def test_missing_id_is_not_conforming(self):
        assert pr.is_conforming("Phish-2024-07-20.Xfinity.Center.Mansfield.MA") is False

    def test_underscore_format_is_not_conforming(self):
        assert pr.is_conforming("2024_07_20 Xfinity Center Mansfield MA") is False


class TestLocationToDots:
    def test_venue_city_state(self):
        assert pr.location_to_dots("Xfinity Center, Mansfield, MA") == "Xfinity.Center.Mansfield.MA"

    def test_multi_word_venue(self):
        assert pr.location_to_dots("Madison Square Garden, New York, NY") == "Madison.Square.Garden.New.York.NY"

    def test_trailing_space_stripped(self):
        assert pr.location_to_dots("Red Rocks Amphitheatre, Morrison, CO ") == "Red.Rocks.Amphitheatre.Morrison.CO"

    def test_times_union_center(self):
        assert pr.location_to_dots("Times Union Center, Albany, NY") == "Times.Union.Center.Albany.NY"


class TestToCanonicalName:
    def test_assembles_correctly(self):
        assert pr.to_canonical_name("2024-07-20", "Xfinity.Center.Mansfield.MA", "2259") == \
            "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]"

    def test_albany_show(self):
        assert pr.to_canonical_name("2009-11-27", "Times.Union.Center.Albany.NY", "515") == \
            "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]"


class TestParseSearchResults:
    def test_returns_non_4k_result(self):
        results = pr.parse_search_results(FIXTURE_HTML_TWO_RESULTS)
        assert len(results) == 1
        assert results[0] == ("2259", "Xfinity Center, Mansfield, MA")

    def test_single_result(self):
        results = pr.parse_search_results(FIXTURE_HTML_ONE_RESULT)
        assert len(results) == 1
        assert results[0] == ("515", "Times Union Center, Albany, NY")

    def test_no_results_returns_empty(self):
        results = pr.parse_search_results(FIXTURE_HTML_NO_RESULTS)
        assert results == []

    def test_location_strips_date_prefix(self):
        results = pr.parse_search_results(FIXTURE_HTML_ONE_RESULT)
        _, location = results[0]
        assert not location.startswith("11/")


class TestSearchLivephish:
    def test_calls_correct_url(self):
        mock_resp = MagicMock()
        mock_resp.text = FIXTURE_HTML_ONE_RESULT
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = pr.search_livephish("2009-11-27")
        url = mock_get.call_args[0][0]
        assert "q=2009-11-27" in url
        assert result == FIXTURE_HTML_ONE_RESULT

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                pr.search_livephish("2024-01-01")


class TestPickBestMatch:
    def test_returns_first_candidate(self):
        candidates = [("2259", "Xfinity Center, Mansfield, MA"), ("9999", "Other Venue")]
        assert pr.pick_best_match(candidates) == ("2259", "Xfinity Center, Mansfield, MA")

    def test_returns_none_for_empty(self):
        assert pr.pick_best_match([]) is None


class TestMainLogic:
    def _make_dir(self, parent, name):
        d = Path(parent) / name
        d.mkdir()
        return d

    def test_dry_run_prints_rename_no_filesystem_change(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "DRY RUN" in captured.out
            assert "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]" in captured.out
            assert (Path(tmp) / "2024-07-20 Xfinity Center Mansfield MA").exists()

    def test_execute_renames_directory(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            assert not (Path(tmp) / "2024-07-20 Xfinity Center Mansfield MA").exists()
            assert (Path(tmp) / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]").exists()

    def test_skips_conforming_silently(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]")
            with patch.object(pr, "search_livephish") as mock_search:
                pr.main_logic(Path(tmp), dry_run=True)
            mock_search.assert_not_called()
            captured = capsys.readouterr()
            assert "DRY RUN" not in captured.out

    def test_warns_when_not_found(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_NO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found" in captured.err

    def test_http_error_warns_and_counts_as_not_found(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", side_effect=Exception("503")):
                pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "HTTP error" in captured.err
            assert "skipped (not found" in captured.out

    def test_skips_unrecognized_silently(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Live Bait Vol 10")
            with patch.object(pr, "search_livephish") as mock_search:
                pr.main_logic(Path(tmp), dry_run=True)
            mock_search.assert_not_called()

    def test_underscore_date_format(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024_07_20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            assert (Path(tmp) / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]").exists()

    def test_skips_when_destination_exists(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            self._make_dir(tmp, "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            captured = capsys.readouterr()
            assert "already exists" in captured.err
            assert (Path(tmp) / "2024-07-20 Xfinity Center Mansfield MA").exists()
