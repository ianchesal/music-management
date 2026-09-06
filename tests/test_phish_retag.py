import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import mutagen
import pytest


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-retag"
    loader = SourceFileLoader("phish_retag", str(path))
    spec = importlib.util.spec_from_loader("phish_retag", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pt = load_module()


class TestParseShowDirname:
    def test_canonical_name(self):
        assert pt.parse_show_dirname(
            "Phish-2026-07-22.Madison.Square.Garden.New.York.NY.[2761]"
        ) == ("2026-07-22", "Madison.Square.Garden.New.York.NY", "2761")

    def test_international_show(self):
        assert pt.parse_show_dirname(
            "Phish-2026-01-28.Moon.Palace.Resort.Riviera.Maya.MX.[2675]"
        ) == ("2026-01-28", "Moon.Palace.Resort.Riviera.Maya.MX", "2675")

    def test_non_two_letter_ending_still_parses(self):
        assert pt.parse_show_dirname(
            "Phish-2000-06-14.Drum.Logos.Fukuoka.Japan.[123]"
        ) == ("2000-06-14", "Drum.Logos.Fukuoka.Japan", "123")

    def test_live_bait_returns_none(self):
        assert pt.parse_show_dirname("Live Bait Vol. 09") is None

    def test_missing_id_returns_none(self):
        assert pt.parse_show_dirname("Phish-2024-07-20.Xfinity.Center.Mansfield.MA") is None

    def test_undated_returns_none(self):
        assert pt.parse_show_dirname("A Live One") is None


class TestLocationToDots:
    def test_venue_city_state(self):
        assert pt.location_to_dots("Xfinity Center, Mansfield, MA") == "Xfinity.Center.Mansfield.MA"

    def test_dotted_city_produces_double_dot(self):
        assert pt.location_to_dots("Chaifetz Arena, St. Louis, MO") == "Chaifetz.Arena.St..Louis.MO"


class TestDotNormalize:
    def test_collapses_repeated_dots(self):
        assert pt.dot_normalize("St..Louis.MO") == "St.Louis.MO"

    def test_leaves_single_dots_alone(self):
        assert pt.dot_normalize("New.York.NY") == "New.York.NY"


class TestParseDateToken:
    def test_slash_separated(self):
        assert pt.parse_date_token("1994/05/07 I Dallas, TX") == (1994, 5, 7)

    def test_dash_separated(self):
        assert pt.parse_date_token("1992-12-01 I Denison University") == (1992, 12, 1)

    def test_non_zero_padded_day(self):
        assert pt.parse_date_token("1996/12/6 I Las Vegas, NV") == (1996, 12, 6)

    def test_no_leading_date_returns_none(self):
        assert pt.parse_date_token("XL Center, Hartford, CT") is None

    def test_empty_string_returns_none(self):
        assert pt.parse_date_token("") is None

    def test_none_returns_none(self):
        assert pt.parse_date_token(None) is None

    def test_date_must_be_followed_by_boundary(self):
        # "19940507" glued to more digits isn't a recognizable date token.
        assert pt.parse_date_token("19940507extra Dallas, TX") is None


class TestStripDateToken:
    def test_strips_date_and_leading_space(self):
        assert pt.strip_date_token("1994/05/07 I Dallas, TX") == "I Dallas, TX"

    def test_no_date_returns_none(self):
        assert pt.strip_date_token("XL Center, Hartford, CT") is None


class TestMatchSetMarker:
    def test_marker_i(self):
        assert pt.match_set_marker("I Providence, RI") == (1, "Providence, RI")

    def test_marker_ii(self):
        assert pt.match_set_marker("II Providence, RI") == (2, "Providence, RI")

    def test_marker_iii(self):
        assert pt.match_set_marker("III Rosemont, IL") == (3, "Rosemont, IL")

    def test_marker_iv(self):
        assert pt.match_set_marker("IV Super Ball IX, NY") == (4, "Super Ball IX, NY")

    def test_marker_v(self):
        assert pt.match_set_marker("V Something, ZZ") == (5, "Something, ZZ")

    def test_xl_is_not_a_marker(self):
        # "XL" is a technically-valid Roman numeral (40) but not in the
        # allow-list — regression for the real XL Center Hartford directory.
        assert pt.match_set_marker("XL Center, Hartford, CT") is None

    def test_marker_must_be_whole_token(self):
        # "III" glued to more letters isn't a marker.
        assert pt.match_set_marker("IIIrd Anniversary, Boston, MA") is None

    def test_no_marker_at_all(self):
        assert pt.match_set_marker("Chicago, IL (soundcheck)") is None


class TestClassifyCleanMultiset:
    def test_two_set_show(self):
        assert pt.classify_clean_multiset(
            ["1994/05/07 I Dallas, TX", "1994/05/07 II Dallas, TX"],
            "1994-05-07",
        ) == {"1994/05/07 I Dallas, TX": 1, "1994/05/07 II Dallas, TX": 2}

    def test_three_set_show(self):
        assert pt.classify_clean_multiset(
            ["1995/12/31 I New York, NY", "1995/12/31 II New York, NY",
             "1995/12/31 III New York, NY"],
            "1995-12-31",
        ) == {"1995/12/31 I New York, NY": 1, "1995/12/31 II New York, NY": 2,
              "1995/12/31 III New York, NY": 3}

    def test_four_set_show(self):
        # Real show: Super Ball IX, 2011-07-02, four sets.
        tags = ["2011/07/02 I Super Ball IX, NY", "2011/07/02 II Super Ball IX, NY",
                "2011/07/02 III Super Ball IX, NY", "2011/07/02 IV Super Ball IX, NY"]
        result = pt.classify_clean_multiset(tags, "2011-07-02")
        assert result == {tags[0]: 1, tags[1]: 2, tags[2]: 3, tags[3]: 4}

    def test_non_zero_padded_date_still_matches(self):
        assert pt.classify_clean_multiset(
            ["1996/12/6 I Las Vegas, NV", "1996/12/6 II Las Vegas, NV"],
            "1996-12-06",
        ) == {"1996/12/6 I Las Vegas, NV": 1, "1996/12/6 II Las Vegas, NV": 2}

    def test_mismatched_date_is_anomaly(self):
        # Real contamination shape: a bonus track from a different show/date.
        tags = ["1994/12/01 I Salem, OR", "1994/12/01 II Salem, OR",
                "1994/11/12 II Kent, OH"]
        assert pt.classify_clean_multiset(tags, "1994-12-01") is None

    def test_missing_marker_is_anomaly(self):
        # Soundcheck-style tag alongside otherwise-clean sets.
        tags = ["1994/06/18 Chicago, IL (soundcheck)",
                "1994/06/18 I Chicago, IL", "1994/06/18 II Chicago, IL"]
        assert pt.classify_clean_multiset(tags, "1994-06-18") is None

    def test_xl_center_style_tags_are_anomaly(self):
        # Regression: two distinct tags on the real XL Center directory
        # shape, neither a genuine set marker.
        tags = ["2013/10/27 XL Center, Hartford, CT",
                "2013/10/27 XL Center, Hartford, CT (soundcheck)"]
        assert pt.classify_clean_multiset(tags, "2013-10-27") is None

    def test_remainder_mismatch_is_anomaly(self):
        # Valid markers on both, but they disagree on venue/city text.
        tags = ["1994/05/07 I Dallas, TX", "1994/05/07 II Fort Worth, TX"]
        assert pt.classify_clean_multiset(tags, "1994-05-07") is None

    def test_casing_only_difference_with_no_marker_is_anomaly(self):
        # Real data: two files differing only by tag casing, no set marker.
        tags = ["2017/07/14 Chicago, IL", "2017/07/14 Chicago, Il"]
        assert pt.classify_clean_multiset(tags, "2017-07-14") is None


class TestSplitVenueCity:
    def test_simple_city(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Noblesville, IN"
        ) == "Ruoff Music Center, Noblesville, IN"

    def test_multi_word_city_longest_match_wins(self):
        # Shortest-suffix matching would wrongly split "...Garden New, York, NY".
        assert pt.split_venue_city(
            "Madison.Square.Garden.New.York.NY", "2026/07/22 New York, NY"
        ) == "Madison Square Garden, New York, NY"

    def test_mexico_show(self):
        assert pt.split_venue_city(
            "Moon.Palace.Resort.Riviera.Maya.MX", "2026/01/28 Riviera Maya, MX"
        ) == "Moon Palace Resort, Riviera Maya, MX"

    def test_messy_tag_with_prefix_and_trailing_junk(self):
        assert pt.split_venue_city(
            "Empower.Federal.Credit.Union.Amphitheater.at.Lakeview.Syracuse.NY",
            "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)",
        ) == "Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"

    def test_set_numeral_tag(self):
        assert pt.split_venue_city(
            "Providence.Civic.Center.Providence.RI", "1994/12/29 I Providence, RI"
        ) == "Providence Civic Center, Providence, RI"

    def test_two_comma_tag_city_is_last_segment(self):
        # City must be "Hampton", not "Hampton Coliseum, Hampton".
        assert pt.split_venue_city(
            "Hampton.Coliseum.Hampton.VA", "1997/11/22 Hampton Coliseum, Hampton, VA"
        ) == "Hampton Coliseum, Hampton, VA"

    def test_dotted_city_st_louis(self):
        assert pt.split_venue_city(
            "Chaifetz.Arena.St.Louis.MO", "2024/07/30 St. Louis, MO"
        ) == "Chaifetz Arena, St. Louis, MO"

    def test_state_mismatch_returns_none(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Noblesville, NY"
        ) is None

    def test_city_not_in_dirname_returns_none(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Indianapolis, IN"
        ) is None

    def test_non_two_letter_ending_returns_none(self):
        assert pt.split_venue_city(
            "Drum.Logos.Fukuoka.Japan", "2000/06/14 Fukuoka, Japan"
        ) is None

    def test_no_tag_returns_none(self):
        assert pt.split_venue_city("Ruoff.Music.Center.Noblesville.IN", None) is None
        assert pt.split_venue_city("Ruoff.Music.Center.Noblesville.IN", "") is None

    def test_empty_venue_returns_none(self):
        # The whole location is the city — no venue to split off.
        assert pt.split_venue_city("Noblesville.IN", "2026/07/12 Noblesville, IN") is None


class TestRoundTripOk:
    def test_exact_round_trip(self):
        assert pt.round_trip_ok(
            "Madison Square Garden, New York, NY",
            "Madison.Square.Garden.New.York.NY",
        ) is True

    def test_dotted_city_round_trip(self):
        assert pt.round_trip_ok(
            "Chaifetz Arena, St. Louis, MO", "Chaifetz.Arena.St.Louis.MO"
        ) is True

    def test_wrong_location_fails(self):
        assert pt.round_trip_ok(
            "Hampton Coliseum, Hampton, VA", "Madison.Square.Garden.New.York.NY"
        ) is False

    def test_dicks_apostrophe_quirk_round_trips(self):
        # livephish's official name carries an apostrophe; this collection's
        # directory names strip it. One-off exception, not a real mismatch.
        assert pt.round_trip_ok(
            "Dick's Sporting Goods Park, Commerce City, CO",
            "Dicks.Sporting.Goods.Park.Commerce.City.CO",
        ) is True

    def test_dicks_apostrophe_quirk_round_trips_when_dir_keeps_apostrophe(self):
        # Some directories keep the apostrophe verbatim rather than stripping
        # it. The quirk must be applied to both sides so either form matches.
        assert pt.round_trip_ok(
            "Dick's Sporting Goods Park, Commerce City, CO",
            "Dick's.Sporting.Goods.Park.Commerce.City.CO",
        ) is True

    def test_other_apostrophes_are_not_silently_stripped(self):
        # The quirk list is a literal one-off, not a general apostrophe
        # stripper — an unrelated apostrophe mismatch should still fail.
        assert pt.round_trip_ok(
            "Bill's Bar, Boston, MA", "Bills.Bar.Boston.MA"
        ) is False


class TestCache:
    def test_default_path_honors_xdg_cache_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert pt.default_cache_path() == tmp_path / "phish-retag.json"

    def test_default_path_falls_back_to_home_cache(self, monkeypatch):
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert pt.default_cache_path() == Path.home() / ".cache" / "phish-retag.json"

    def test_round_trip(self, tmp_path):
        cache_file = tmp_path / "sub" / "cache.json"
        pt.save_cache(cache_file, {"2761": "Madison Square Garden, New York, NY"})
        assert pt.load_cache(cache_file) == {"2761": "Madison Square Garden, New York, NY"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert pt.load_cache(tmp_path / "nope.json") == {}

    def test_corrupt_file_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert pt.load_cache(bad) == {}

    def test_non_dict_json_returns_empty(self, tmp_path):
        bad = tmp_path / "list.json"
        bad.write_text("[1, 2]")
        assert pt.load_cache(bad) == {}

    def test_binary_garbage_file_returns_empty(self, tmp_path):
        bad = tmp_path / "bin.json"
        bad.write_bytes(b"\xff\xfe\x00garbage")
        assert pt.load_cache(bad) == {}


FIXTURE_HTML_SEARCH = """
<html><body>
<a href="/LP-2761.html"><img alt="07/22/26 Madison Square Garden, New York, NY " title="..."></a>
<a href="/LP-2761.html">Phish</a>
<a href="/LP-2762.html"><img alt="07/22/26 Madison Square Garden 4k, New York 4k, NY " title="..."></a>
<a href="/LP-2762.html">Phish</a>
<a href="/LP-9999.html"><img alt="07/22/26 Some Other Venue, Elsewhere, CA " title="..."></a>
<a href="/LP-9999.html">Phish</a>
</body></html>
"""


class TestLivephishLocation:
    def test_returns_location_for_matching_id(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep") as mock_sleep:
            loc = pt.livephish_location("2026-07-22", "2761")
        assert loc == "Madison Square Garden, New York, NY"
        mock_sleep.assert_called_once()

    def test_jitter_delay_is_within_bounds(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep") as mock_sleep:
            pt.livephish_location("2026-07-22", "2761")
        (delay,), _ = mock_sleep.call_args
        assert 0.5 <= delay <= 1.5

    def test_no_matching_id_returns_none(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep"):
            assert pt.livephish_location("2026-07-22", "1234") is None

    def test_http_error_returns_none(self):
        with patch.object(pt, "search_livephish", side_effect=Exception("boom")), \
             patch.object(pt.time, "sleep") as mock_sleep:
            assert pt.livephish_location("2026-07-22", "2761") is None
        mock_sleep.assert_called_once()  # still polite after a failed request

    def test_4k_variants_are_skipped(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep"):
            assert pt.livephish_location("2026-07-22", "2762") is None


class TestTargetAlbum:
    def test_formats_date_with_slashes(self):
        assert pt.target_album("2026-07-22", "Madison Square Garden, New York, NY") \
            == "2026/07/22 Madison Square Garden, New York, NY"


class TestResolveLocation:
    LOC = "Madison.Square.Garden.New.York.NY"
    RESOLVED = "Madison Square Garden, New York, NY"

    def test_valid_cache_hit_skips_network(self, tmp_path):
        cache = {"2761": self.RESOLVED}
        with patch.object(pt, "livephish_location") as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      None, cache, tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_not_called()

    def test_stale_cache_entry_is_discarded_and_reresolved(self, tmp_path):
        cache = {"2761": "Wrong Venue, Elsewhere, CA"}
        with patch.object(pt, "livephish_location", return_value=self.RESOLVED):
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      None, cache, tmp_path / "c.json")
        assert out == self.RESOLVED
        assert cache["2761"] == self.RESOLVED

    def test_heuristic_resolves_offline(self, tmp_path):
        cache = {}
        with patch.object(pt, "livephish_location") as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      "2026/07/22 New York, NY", cache,
                                      tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_not_called()

    def test_resolution_is_persisted_to_cache_file(self, tmp_path):
        cache_file = tmp_path / "c.json"
        pt.resolve_location("2026-07-22", self.LOC, "2761",
                            "2026/07/22 New York, NY", {}, cache_file)
        assert json.loads(cache_file.read_text())["2761"] == self.RESOLVED

    def test_falls_back_to_livephish_when_heuristic_fails(self, tmp_path):
        with patch.object(pt, "livephish_location", return_value=self.RESOLVED) as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      "garbage tag", {}, tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_called_once_with("2026-07-22", "2761")

    def test_livephish_result_failing_round_trip_is_unresolved(self, tmp_path):
        with patch.object(pt, "livephish_location",
                          return_value="Some Other Place, Elsewhere, CA"):
            assert pt.resolve_location("2026-07-22", self.LOC, "2761",
                                       None, {}, tmp_path / "c.json") is None

    def test_livephish_miss_is_unresolved(self, tmp_path):
        with patch.object(pt, "livephish_location", return_value=None):
            assert pt.resolve_location("2026-07-22", self.LOC, "2761",
                                       None, {}, tmp_path / "c.json") is None

    def test_non_two_letter_ending_uses_livephish(self, tmp_path):
        loc = "Drum.Logos.Fukuoka.Japan"
        resolved = "Drum Logos, Fukuoka, Japan"
        with patch.object(pt, "livephish_location", return_value=resolved):
            out = pt.resolve_location("2000-06-14", loc, "123",
                                      "2000/06/14 Fukuoka, Japan", {},
                                      tmp_path / "c.json")
        assert out == resolved


# ── Audio fixtures ─────────────────────────────────────────────────────────────
# mutagen can only edit existing containers, not create them; generate tiny
# real files once per session with ffmpeg (a required repo dependency).

@pytest.fixture(scope="session")
def audio_fixtures(tmp_path_factory):
    src = tmp_path_factory.mktemp("audio-fixtures")
    paths = {}
    for ext in ("flac", "m4a", "mp3"):
        out = src / f"fixture.{ext}"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", "anullsrc=r=8000:cl=mono", "-t", "0.1", str(out)],
            check=True, capture_output=True,
        )
        paths[ext] = out
    return paths


def make_show_file(fixtures, dest_dir, name, album=None, date=None):
    dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures[name.rsplit(".", 1)[1]], dest)
    if album is not None or date is not None:
        audio = mutagen.File(str(dest), easy=True)
        if audio.tags is None:
            audio.add_tags()
        if album is not None:
            audio["album"] = album
        if date is not None:
            audio["date"] = date
        audio.save()
    return dest


class TestTagIO:
    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_write_then_read_album(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.write_album(f, "2026/07/22 Madison Square Garden, New York, NY") is True
        assert pt.read_album(f) == "2026/07/22 Madison Square Garden, New York, NY"

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_missing_album_reads_empty_string(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.read_album(f) == ""

    def test_write_preserves_other_tags(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac")
        audio = mutagen.File(str(f), easy=True)
        audio["title"] = "Tweezer"
        audio["artist"] = "Phish"
        audio["tracknumber"] = "5"
        audio.save()
        pt.write_album(f, "New Album")
        audio = mutagen.File(str(f), easy=True)
        assert audio["title"] == ["Tweezer"]
        assert audio["artist"] == ["Phish"]
        assert audio["tracknumber"] == ["5"]
        assert audio["album"] == ["New Album"]

    def test_unreadable_file_returns_none(self, tmp_path):
        junk = tmp_path / "junk.flac"
        junk.write_bytes(b"not audio at all")
        assert pt.read_album(junk) is None
        assert pt.write_album(junk, "x") is False

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_write_then_read_discnumber(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.write_discnumber(f, "2") is True
        assert pt.read_discnumber(f) == "2"

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_missing_discnumber_reads_empty_string(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.read_discnumber(f) == ""

    def test_discnumber_write_preserves_album(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac",
                           album="1994/05/07 Dallas, TX")
        pt.write_discnumber(f, "1")
        assert pt.read_album(f) == "1994/05/07 Dallas, TX"
        assert pt.read_discnumber(f) == "1"

    def test_unreadable_file_discnumber_returns_none(self, tmp_path):
        junk = tmp_path / "junk.flac"
        junk.write_bytes(b"not audio at all")
        assert pt.read_discnumber(junk) is None
        assert pt.write_discnumber(junk, "1") is False

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_write_then_read_date(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.write_date(f, "1996-12-06") is True
        assert pt.read_date(f) == "1996-12-06"

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_missing_date_reads_empty_string(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.read_date(f) == ""

    def test_date_write_preserves_album(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac",
                           album="1994/05/07 Dallas, TX")
        pt.write_date(f, "1994-05-07")
        assert pt.read_album(f) == "1994/05/07 Dallas, TX"
        assert pt.read_date(f) == "1994-05-07"

    def test_unreadable_file_date_returns_none(self, tmp_path):
        junk = tmp_path / "junk.flac"
        junk.write_bytes(b"not audio at all")
        assert pt.read_date(junk) is None
        assert pt.write_date(junk, "1996-12-06") is False


class TestCollectAudio:
    def test_finds_audio_recursively_and_sorted(self, audio_fixtures, tmp_path):
        make_show_file(audio_fixtures, tmp_path, "b.flac")
        make_show_file(audio_fixtures, tmp_path, "a.mp3")
        make_show_file(audio_fixtures, tmp_path / "disc2", "c.m4a")
        (tmp_path / "folder.jpg").write_bytes(b"\xff")
        (tmp_path / "notes.txt").write_text("setlist")
        found = pt.collect_audio(tmp_path)
        assert [p.name for p in found] == ["a.mp3", "b.flac", "c.m4a"]

    def test_uppercase_extensions_are_found(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac")
        f.rename(tmp_path / "TRACK.FLAC")
        assert [p.name for p in pt.collect_audio(tmp_path)] == ["TRACK.FLAC"]


def build_collection(audio_fixtures, root):
    """A miniature collection covering every per-directory outcome."""
    # Needs retag (heuristic-resolvable from its own tag)
    d1 = root / "Phish-2026-07-21.Empower.Federal.Credit.Union.Amphitheater.at.Lakeview.Syracuse.NY.[2760]"
    make_show_file(audio_fixtures, d1, "t1.flac",
                   album="Phish - Phish - 2026_07_21 Syracuse, NY (Phis)")
    make_show_file(audio_fixtures, d1, "t2.flac",
                   album="Phish - Phish - 2026_07_21 Syracuse, NY (Phis)")
    # Already correct
    d2 = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
    make_show_file(audio_fixtures, d2, "t1.flac",
                   album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                   date="2026-07-12")
    # Clean multi-set: two distinct tags differing only by set marker
    d3 = root / "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]"
    make_show_file(audio_fixtures, d3, "s1.flac", album="1994/12/29 I Providence, RI")
    make_show_file(audio_fixtures, d3, "s2.flac", album="1994/12/29 II Providence, RI")
    # Unresolvable: garbage tag, livephish will be mocked to miss
    d4 = root / "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]"
    make_show_file(audio_fixtures, d4, "t1.flac", album="Big Cypress New Years")
    # Non-canonical: skipped
    d5 = root / "Live Bait Vol. 09"
    make_show_file(audio_fixtures, d5, "t1.flac", album="Live Bait Vol. 09")
    # Multi-set anomaly: real contamination shape — a track internally
    # tagged with a different date/venue mixed into an otherwise-clean pair.
    d6 = root / "Phish-1994-12-01.Salem.Armory.Salem.OR.[359]"
    make_show_file(audio_fixtures, d6, "s1.flac", album="1994/12/01 I Salem, OR")
    make_show_file(audio_fixtures, d6, "s2.flac", album="1994/12/01 II Salem, OR")
    make_show_file(audio_fixtures, d6, "bonus.flac", album="1994/11/12 II Kent, OH")
    return d1, d2, d3, d4, d5, d6


class TestMainLogic:
    def _run(self, root, cache_file, execute):
        with patch.object(pt, "livephish_location", return_value=None):
            return pt.main_logic(root, execute=execute, cache_path=cache_file)

    def test_dry_run_reports_but_does_not_write(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        d1, _, d3, *_ = build_collection(audio_fixtures, root)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 2, "already": 1, "multiset_clean": 1,
                          "multiset_anomaly": 1, "unresolved": 1, "skipped": 1}
        # Tags untouched in dry run
        assert pt.read_album(d1 / "t1.flac") == "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)"
        assert pt.read_album(d3 / "s1.flac") == "1994/12/29 I Providence, RI"
        assert pt.read_discnumber(d3 / "s1.flac") == ""
        out = capsys.readouterr().out
        assert "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY" in out
        assert ("Disc 1: 1994/12/29 I Providence, RI → "
                "1994/12/29 Providence Civic Center, Providence, RI") in out
        assert ("Disc 2: 1994/12/29 II Providence, RI → "
                "1994/12/29 Providence Civic Center, Providence, RI") in out

    def test_dry_run_warms_cache(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        cache_file = tmp_path / "c.json"
        self._run(root, cache_file, execute=False)
        cache = json.loads(cache_file.read_text())
        assert cache["2760"] == "Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"

    def test_execute_writes_album_tags(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, d2, d3, d4, d5, d6 = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        want = "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"
        assert pt.read_album(d1 / "t1.flac") == want
        assert pt.read_album(d1 / "t2.flac") == want
        # clean multi-set: album collapsed, discnumber set per set
        want_multiset = "1994/12/29 Providence Civic Center, Providence, RI"
        assert pt.read_album(d3 / "s1.flac") == want_multiset
        assert pt.read_discnumber(d3 / "s1.flac") == "1"
        assert pt.read_album(d3 / "s2.flac") == want_multiset
        assert pt.read_discnumber(d3 / "s2.flac") == "2"
        # unresolved, non-canonical, and multi-set-anomaly dirs untouched
        assert pt.read_album(d4 / "t1.flac") == "Big Cypress New Years"
        assert pt.read_album(d5 / "t1.flac") == "Live Bait Vol. 09"
        assert pt.read_album(d6 / "s1.flac") == "1994/12/01 I Salem, OR"
        assert pt.read_album(d6 / "bonus.flac") == "1994/11/12 II Kent, OH"

    def test_already_correct_files_keep_mtime_on_execute(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        _, d2, *_ = build_collection(audio_fixtures, root)
        f = d2 / "t1.flac"
        before = f.stat().st_mtime_ns
        self._run(root, tmp_path / "c.json", execute=True)
        assert f.stat().st_mtime_ns == before

    def test_multiset_clean_second_run_is_noop(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d3 = root / "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]"
        make_show_file(audio_fixtures, d3, "s1.flac", album="1994/12/29 I Providence, RI")
        make_show_file(audio_fixtures, d3, "s2.flac", album="1994/12/29 II Providence, RI")
        cache_file = tmp_path / "c.json"
        self._run(root, cache_file, execute=True)
        f = d3 / "s1.flac"
        before = f.stat().st_mtime_ns
        counts = self._run(root, cache_file, execute=True)
        # after execute, both files share one album tag with no discnumber
        # mismatch, so this second run actually exercises the single-tag
        # branch, not the multiset-clean branch directly — still valid
        # end-to-end idempotency coverage.
        assert counts["already"] == 1
        assert counts["multiset_clean"] == 0
        assert f.stat().st_mtime_ns == before

    def test_incomplete_tape_clean_multiset_no_disc_one(self, audio_fixtures, tmp_path):
        # Regression test: a two-set show missing its first-set tape (no "I"
        # tag present, only "II" and "III") still classifies as a clean
        # multi-set show. main_logic must not assume disc 1 exists when
        # picking the source tag for venue resolution — it must pick the
        # lowest disc number actually present (here, 2).
        root = tmp_path / "col"
        d = root / "Phish-1994-12-01.Salem.Armory.Salem.OR.[360]"
        make_show_file(audio_fixtures, d, "s2.flac", album="1994/12/01 II Salem, OR")
        make_show_file(audio_fixtures, d, "s3.flac", album="1994/12/01 III Salem, OR")
        counts = self._run(root, tmp_path / "c.json", execute=True)
        assert counts["multiset_clean"] == 1
        want = "1994/12/01 Salem Armory, Salem, OR"
        assert pt.read_album(d / "s2.flac") == want
        assert pt.read_discnumber(d / "s2.flac") == "2"
        assert pt.read_album(d / "s3.flac") == want
        assert pt.read_discnumber(d / "s3.flac") == "3"

    def test_clean_multiset_unresolved_venue(self, audio_fixtures, tmp_path):
        # Clean multi-set show (matching date, valid I/II markers, identical
        # remainder) whose location text has no "City, ST" the heuristic can
        # split out, and livephish is mocked to miss — resolution fails and
        # the directory lands in the shared unresolved bucket. Garbage
        # remainder deliberately mirrors the existing unresolved fixture d4
        # ("Big Cypress New Years").
        root = tmp_path / "col"
        d = root / "Phish-1996-08-16.Some.Random.Field.[555]"
        make_show_file(audio_fixtures, d, "s1.flac", album="1996/08/16 I Loop Fest Nonsense")
        make_show_file(audio_fixtures, d, "s2.flac", album="1996/08/16 II Loop Fest Nonsense")
        counts = self._run(root, tmp_path / "c.json", execute=True)
        assert counts["unresolved"] == 1
        assert counts["multiset_clean"] == 0
        assert counts["updated"] == 0
        assert pt.read_album(d / "s1.flac") == "1996/08/16 I Loop Fest Nonsense"
        assert pt.read_album(d / "s2.flac") == "1996/08/16 II Loop Fest Nonsense"
        assert pt.read_discnumber(d / "s1.flac") == ""
        assert pt.read_discnumber(d / "s2.flac") == ""

    def test_multiset_anomaly_warning_lists_distinct_tags(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        err = capsys.readouterr().err
        assert "1994/12/01 I Salem, OR" in err
        assert "1994/12/01 II Salem, OR" in err
        assert "1994/11/12 II Kent, OH" in err

    def test_summary_lists_multiset_anomaly_and_unresolved_dirs(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        out = capsys.readouterr().out
        assert "Phish-1994-12-01.Salem.Armory.Salem.OR.[359]" in out
        assert "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]" in out

    def test_empty_dir_counts_as_skipped(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        (root / "Phish-2026-07-22.Madison.Square.Garden.New.York.NY.[2761]").mkdir(parents=True)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 0, "already": 0, "multiset_clean": 0,
                          "multiset_anomaly": 0, "unresolved": 0, "skipped": 1}


class TestStateCache:
    def _run(self, root, cache_file, state_file, execute, rescan=False):
        with patch.object(pt, "livephish_location", return_value=None):
            return pt.main_logic(root, execute=execute, cache_path=cache_file,
                                  state_path=state_file, rescan=rescan)

    def _correct_show(self, audio_fixtures, root):
        d = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
        make_show_file(audio_fixtures, d, "t1.flac",
                       album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                       date="2026-07-12")
        return d

    def test_already_correct_dir_skips_tag_reads_on_rerun(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        self._correct_show(audio_fixtures, root)
        cache_file, state_file = tmp_path / "c.json", tmp_path / "s.json"
        counts = self._run(root, cache_file, state_file, execute=False)
        assert counts["already"] == 1
        with patch.object(pt, "read_album") as mock_read:
            counts = self._run(root, cache_file, state_file, execute=False)
        mock_read.assert_not_called()
        assert counts["already"] == 1

    def test_changed_directory_bypasses_cache(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d = self._correct_show(audio_fixtures, root)
        cache_file, state_file = tmp_path / "c.json", tmp_path / "s.json"
        self._run(root, cache_file, state_file, execute=False)
        make_show_file(audio_fixtures, d, "t2.flac",
                       album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                       date="2026-07-12")
        with patch.object(pt, "read_album") as mock_read:
            mock_read.return_value = "2026/07/12 Ruoff Music Center, Noblesville, IN"
            self._run(root, cache_file, state_file, execute=False)
        mock_read.assert_called()

    def test_rescan_ignores_cache(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        self._correct_show(audio_fixtures, root)
        cache_file, state_file = tmp_path / "c.json", tmp_path / "s.json"
        self._run(root, cache_file, state_file, execute=False)
        with patch.object(pt, "read_album") as mock_read:
            mock_read.return_value = "2026/07/12 Ruoff Music Center, Noblesville, IN"
            self._run(root, cache_file, state_file, execute=False, rescan=True)
        mock_read.assert_called()

    def test_dry_run_pending_update_is_not_cached(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, *_ = build_collection(audio_fixtures, root)
        cache_file, state_file = tmp_path / "c.json", tmp_path / "s.json"
        self._run(root, cache_file, state_file, execute=False)
        with patch.object(pt, "read_album") as mock_read:
            mock_read.return_value = "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)"
            self._run(root, cache_file, state_file, execute=False)
        mock_read.assert_called()

    def test_execute_caches_result_as_already(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, *_ = build_collection(audio_fixtures, root)
        cache_file, state_file = tmp_path / "c.json", tmp_path / "s.json"
        self._run(root, cache_file, state_file, execute=True)
        with patch.object(pt, "read_album") as mock_read:
            counts = self._run(root, cache_file, state_file, execute=False)
        mock_read.assert_not_called()
        assert counts["already"] >= 1

    def test_no_state_path_disables_caching(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        self._correct_show(audio_fixtures, root)
        cache_file = tmp_path / "c.json"
        with patch.object(pt, "livephish_location", return_value=None):
            pt.main_logic(root, execute=False, cache_path=cache_file)
            with patch.object(pt, "read_album") as mock_read:
                mock_read.return_value = "2026/07/12 Ruoff Music Center, Noblesville, IN"
                pt.main_logic(root, execute=False, cache_path=cache_file)
        mock_read.assert_called()


class TestDateNormalization:
    def _run(self, root, cache_file, execute):
        with patch.object(pt, "livephish_location", return_value=None):
            return pt.main_logic(root, execute=execute, cache_path=cache_file)

    def test_wrong_date_triggers_update_even_when_album_correct(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
        make_show_file(audio_fixtures, d, "t1.flac",
                       album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                       date="2026-07-11")
        counts = self._run(root, tmp_path / "c.json", execute=True)
        assert counts["updated"] == 1
        assert counts["already"] == 0
        assert pt.read_album(d / "t1.flac") == "2026/07/12 Ruoff Music Center, Noblesville, IN"
        assert pt.read_date(d / "t1.flac") == "2026-07-12"

    def test_missing_date_is_set_alongside_album_fix(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, d2, *_ = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        assert pt.read_date(d1 / "t1.flac") == "2026-07-21"
        assert pt.read_date(d1 / "t2.flac") == "2026-07-21"

    def test_clean_multiset_gets_date_set_on_every_file(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        _, _, d3, *_ = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        assert pt.read_date(d3 / "s1.flac") == "1994-12-29"
        assert pt.read_date(d3 / "s2.flac") == "1994-12-29"

    def test_unresolved_and_anomaly_dirs_leave_date_untouched(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        _, _, _, d4, _, d6 = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        assert pt.read_date(d4 / "t1.flac") == ""
        assert pt.read_date(d6 / "s1.flac") == ""

    def test_dry_run_does_not_write_date(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
        make_show_file(audio_fixtures, d, "t1.flac",
                       album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                       date="2026-07-11")
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts["updated"] == 1
        assert pt.read_date(d / "t1.flac") == "2026-07-11"

    def test_dry_run_prints_date_diff(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        d = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
        make_show_file(audio_fixtures, d, "t1.flac",
                       album="2026/07/12 Ruoff Music Center, Noblesville, IN",
                       date="2026-07-11")
        self._run(root, tmp_path / "c.json", execute=False)
        out = capsys.readouterr().out
        assert "2026-07-11 → 2026-07-12" in out


class TestParseArgs:
    def test_defaults(self):
        path, execute, cache, state, rescan = pt.parse_args(["phish-retag"])
        assert path == pt.DEFAULT_PATH
        assert execute is False
        assert cache == pt.default_cache_path()
        assert state == pt.default_state_path()
        assert rescan is False

    def test_positional_path_and_execute(self, tmp_path):
        path, execute, *_ = pt.parse_args(["phish-retag", str(tmp_path), "--execute"])
        assert path == tmp_path
        assert execute is True

    def test_cache_flag(self, tmp_path):
        _, _, cache, _, _ = pt.parse_args(["phish-retag", str(tmp_path), "--cache", "/tmp/x.json"])
        assert cache == Path("/tmp/x.json")

    def test_state_flag(self, tmp_path):
        _, _, _, state, _ = pt.parse_args(["phish-retag", str(tmp_path), "--state", "/tmp/s.json"])
        assert state == Path("/tmp/s.json")

    def test_rescan_flag(self, tmp_path):
        *_, rescan = pt.parse_args(["phish-retag", str(tmp_path), "--rescan"])
        assert rescan is True

    def test_unknown_flag_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pt.parse_args(["phish-retag", str(tmp_path), "--bogus"])
