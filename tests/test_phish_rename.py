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

FIXTURE_HTML_MISMATCHED_LOCATION = """
<html><body>
<a href="/LP-1669.html"><img alt="10/10/99 MGM Grand Garden Arena, Las Vegas, NV " title="..."></a>
<a href="/LP-1669.html">Phish</a>
</body></html>
"""

# livephish.com's search is fuzzy text matching, not a strict date filter —
# it can return results whose actual date doesn't match the query at all.
FIXTURE_HTML_WRONG_DATE_RESULTS = """
<html><body>
<a href="/LP-1669.html"><img alt="10/28/21 MGM Grand Garden Arena, Las Vegas, NV " title="..."></a>
<a href="/LP-1669.html">Phish</a>
<a href="/LP-486.html"><img alt="07/10/99 E Center, Camden, NJ " title="..."></a>
<a href="/LP-486.html">Phish</a>
</body></html>
"""

FIXTURE_HTML_SECOND_CANDIDATE_MATCHES = """
<html><body>
<a href="/LP-1111.html"><img alt="07/20/24 Other Venue, Somewhere, ZZ " title="..."></a>
<a href="/LP-1111.html">Phish</a>
<a href="/LP-2259.html"><img alt="07/20/24 Xfinity Center, Mansfield, MA " title="..."></a>
<a href="/LP-2259.html">Phish</a>
</body></html>
"""

FIXTURE_PHISHNET_SHOW = """
<html><body>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "Event",
  "startDate" : "1999-10-10T20:00",
  "location" : {
    "@type" : "Place",
    "name": "Pepsi Arena",
    "address": "Albany, NY"
  }
}
</script>
</body></html>
"""


class TestDateFromDirname:
    def test_yyyy_dash_mm_dd(self):
        assert pr.date_from_dirname("2024-07-20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_yyyy_underscore_mm_dd(self):
        assert pr.date_from_dirname("2024_07_20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_yyyy_dot_mm_dd(self):
        assert pr.date_from_dirname("2024.07.20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_single_digit_month(self):
        assert pr.date_from_dirname("1994_6_19 Somewhere") == "1994-06-19"

    def test_single_digit_day(self):
        assert pr.date_from_dirname("1994-12-6 Goleta, CA") == "1994-12-06"

    def test_conforming_name_still_extracts_date(self):
        # main_logic never calls this for conforming names (is_conforming is
        # checked first), but the extraction itself is now prefix-agnostic.
        assert pr.date_from_dirname("Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]") == "2024-07-20"

    def test_hand_named_with_phish_prefix_no_id(self):
        assert pr.date_from_dirname("Phish-2026-09-04.Dicks.Sporting.Goods.Park.Commerce.City.CO") == "2026-09-04"

    def test_undated_returns_none(self):
        assert pr.date_from_dirname("Live Bait Vol 10") is None

    def test_id_bracket_not_mistaken_for_date(self):
        assert pr.date_from_dirname("Some.Show.[2259]") is None


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


class TestAltTextDate:
    def test_two_digit_year_90s(self):
        assert pr.alt_text_date("07/10/99 E Center, Camden, NJ") == "1999-07-10"

    def test_two_digit_year_2000s(self):
        assert pr.alt_text_date("10/28/21 MGM Grand Garden Arena, Las Vegas, NV") == "2021-10-28"

    def test_four_digit_year(self):
        assert pr.alt_text_date("07/20/2024 Xfinity Center, Mansfield, MA") == "2024-07-20"

    def test_no_leading_date_returns_none(self):
        assert pr.alt_text_date("Xfinity Center, Mansfield, MA") is None


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

    def test_expected_date_filters_out_unrelated_results(self):
        # livephish.com's fuzzy search can return results for a date nobody
        # asked about; expected_date should drop anything that doesn't match.
        results = pr.parse_search_results(FIXTURE_HTML_WRONG_DATE_RESULTS, expected_date="1999-10-10")
        assert results == []

    def test_expected_date_keeps_matching_result(self):
        results = pr.parse_search_results(FIXTURE_HTML_TWO_RESULTS, expected_date="2024-07-20")
        assert len(results) == 1
        assert results[0] == ("2259", "Xfinity Center, Mansfield, MA")


class TestSearchLivephish:
    # patches the shared requests module; works because phish-rename uses
    # "import requests", not "from requests import get"
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


class TestFetchPhishnetShow:
    def test_returns_none_on_404(self):
        mock_resp = MagicMock(status_code=404)
        with patch("requests.get", return_value=mock_resp):
            assert pr.fetch_phishnet_show("2000-01-02") is None

    def test_returns_html_on_success(self):
        mock_resp = MagicMock(status_code=200, text=FIXTURE_PHISHNET_SHOW)
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = pr.fetch_phishnet_show("1999-10-10")
        url = mock_get.call_args[0][0]
        assert "d=1999-10-10" in url
        assert result == FIXTURE_PHISHNET_SHOW

    def test_raises_on_other_http_error(self):
        mock_resp = MagicMock(status_code=500)
        mock_resp.raise_for_status.side_effect = Exception("500")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="500"):
                pr.fetch_phishnet_show("1999-10-10")


class TestParsePhishnetLocation:
    def test_extracts_venue_and_address(self):
        assert pr.parse_phishnet_location(FIXTURE_PHISHNET_SHOW) == "Pepsi Arena, Albany, NY"

    def test_returns_none_without_ld_json(self):
        assert pr.parse_phishnet_location("<html><body>nothing here</body></html>") is None

    def test_returns_none_on_malformed_json(self):
        html = '<script type="application/ld+json">{not valid json</script>'
        assert pr.parse_phishnet_location(html) is None


class TestLocationMatches:
    def test_mismatched_state_and_venue(self):
        assert pr.location_matches("Phish-1999-10-10.Albany.NY", "MGM Grand Garden Arena, Las Vegas, NV") is False

    def test_mismatched_city(self):
        assert pr.location_matches("Phish-2023-07-23.Syracuse.NY", "Higher Ground, Burlington, VT") is False

    def test_matching_city_state(self):
        assert pr.location_matches("Phish-2023-08-31.Commerce.City.CO", "Dick's Sporting Goods Park, Commerce City, CO") is True

    def test_matching_hand_named_apostrophe_variant(self):
        assert pr.location_matches(
            "Phish-2026-09-04.Dicks.Sporting.Goods.Park.Commerce.City.CO",
            "Dick's Sporting Goods Park, Commerce City, CO",
        ) is True

    def test_no_hint_always_matches(self):
        assert pr.location_matches("Phish-2024-07-20", "Xfinity Center, Mansfield, MA") is True

    def test_generic_words_alone_dont_count_as_a_match(self):
        assert pr.location_matches("Phish-1997-12-11.War.Memorial", "Memorial Auditorium, Somewhere, ZZ") is False

    def test_shared_state_code_alone_is_not_a_match(self):
        assert pr.location_matches("Phish-2023-07-23.Syracuse.NY", "Madison Square Garden, New York, NY") is False


class TestPickBestMatch:
    def test_returns_first_candidate(self):
        candidates = [("2259", "Xfinity Center, Mansfield, MA"), ("9999", "Other Venue")]
        assert pr.pick_best_match(candidates) == ("2259", "Xfinity Center, Mansfield, MA")

    def test_returns_none_for_empty(self):
        assert pr.pick_best_match([]) is None

    def test_prefers_candidate_matching_dirname_location(self):
        candidates = [("1111", "Other Venue, Somewhere, ZZ"), ("2259", "Xfinity Center, Mansfield, MA")]
        assert pr.pick_best_match(candidates, "2024-07-20 Xfinity Center Mansfield MA") == ("2259", "Xfinity Center, Mansfield, MA")

    def test_falls_back_to_first_when_none_match(self):
        candidates = [("1111", "Other Venue, Somewhere, ZZ"), ("2222", "Another Venue, Elsewhere, YY")]
        assert pr.pick_best_match(candidates, "Phish-1999-10-10.Albany.NY") == ("1111", "Other Venue, Somewhere, ZZ")


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
                with patch.object(pr, "fetch_phishnet_show", return_value=None):
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

    def test_hand_named_dir_with_id_missing_gets_renamed(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-2026-09-04.Dicks.Sporting.Goods.Park.Commerce.City.CO")
            html = """
            <html><body>
            <a href="/LP-2768.html"><img alt="09/04/26 Dick's Sporting Goods Park, Commerce City, CO " title="..."></a>
            <a href="/LP-2768.html">Phish</a>
            </body></html>
            """
            with patch.object(pr, "search_livephish", return_value=html):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            assert (Path(tmp) / "Phish-2026-09-04.Dick's.Sporting.Goods.Park.Commerce.City.CO.[2768]").exists()

    def test_location_mismatch_is_skipped_not_renamed(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-1999-10-10.Albany.NY")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_MISMATCHED_LOCATION):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "location mismatch" in captured.err
            assert "DRY RUN" not in captured.out
            assert (Path(tmp) / "Phish-1999-10-10.Albany.NY").exists()

    def test_not_found_falls_back_to_phishnet_for_context(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-1999-10-10.Albany.NY")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_WRONG_DATE_RESULTS):
                with patch.object(pr, "fetch_phishnet_show", return_value=FIXTURE_PHISHNET_SHOW):
                    with patch("time.sleep"):
                        pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found on livephish.com" in captured.err
            assert "phish.net confirms this show: Pepsi Arena, Albany, NY" in captured.err
            assert (Path(tmp) / "Phish-1999-10-10.Albany.NY").exists()

    def test_not_found_with_no_phishnet_info_still_warns_plainly(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-1999-10-10.Albany.NY")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_NO_RESULTS):
                with patch.object(pr, "fetch_phishnet_show", return_value=None):
                    with patch("time.sleep"):
                        pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found on livephish.com" in captured.err
            assert "phish.net" not in captured.err

    def test_phishnet_lookup_failure_does_not_break_not_found_warning(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-1999-10-10.Albany.NY")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_NO_RESULTS):
                with patch.object(pr, "fetch_phishnet_show", side_effect=Exception("boom")):
                    with patch("time.sleep"):
                        pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found on livephish.com" in captured.err

    def test_fuzzy_search_results_for_wrong_date_are_not_found(self, capsys):
        # Regression: livephish.com's search returned results for 10/28/21
        # and 07/10/99 when asked about 1999-10-10 — a date it has no show
        # for at all. Those must be filtered out as "not found", not treated
        # as a match (whether or not their location happens to look wrong).
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-1999-10-10.Albany.NY")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_WRONG_DATE_RESULTS):
                with patch.object(pr, "fetch_phishnet_show", return_value=None):
                    with patch("time.sleep"):
                        pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found on livephish.com" in captured.err
            assert "location mismatch" not in captured.err
            assert (Path(tmp) / "Phish-1999-10-10.Albany.NY").exists()

    def test_picks_matching_candidate_over_first_result(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_SECOND_CANDIDATE_MATCHES):
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


class TestParseArgs:
    def test_path_and_dry_run_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, dry_run = pr.parse_args(["phish-rename", tmp])
        assert str(path) == tmp
        assert dry_run is True

    def test_explicit_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, dry_run = pr.parse_args(["phish-rename", tmp, "--dry-run"])
        assert dry_run is True

    def test_execute_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, dry_run = pr.parse_args(["phish-rename", tmp, "--execute"])
        assert dry_run is False

    def test_missing_path_exits(self):
        with pytest.raises(SystemExit):
            pr.parse_args(["phish-rename"])

    def test_nonexistent_path_exits(self):
        with pytest.raises(SystemExit):
            pr.parse_args(["phish-rename", "/nonexistent/path/xyz"])

    def test_unknown_arg_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit):
                pr.parse_args(["phish-rename", tmp, "--unknown"])
