import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def make_show_file(fixtures, dest_dir, name, album=None):
    dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures[name.rsplit(".", 1)[1]], dest)
    if album is not None:
        audio = mutagen.File(str(dest), easy=True)
        if audio.tags is None:
            audio.add_tags()
        audio["album"] = album
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
