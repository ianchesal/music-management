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
