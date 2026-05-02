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

    def test_filters_4k_results(self):
        results = pr.parse_search_results(FIXTURE_HTML_TWO_RESULTS)
        ids = [r[0] for r in results]
        assert "2351" not in ids

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
