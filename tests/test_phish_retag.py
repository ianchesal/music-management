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
