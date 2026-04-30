import importlib.util
import sys
import pytest
from pathlib import Path
import tempfile


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-merge"
    loader = SourceFileLoader("phish_merge", str(path))
    spec = importlib.util.spec_from_loader("phish_merge", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pm = load_module()


class TestDateFromExisting:
    def test_yyyy_mm_dd_space_city(self):
        assert pm.date_from_existing("2009-11-27 Albany, NY") == "2009-11-27"

    def test_yyyy_underscore_mm_dd(self):
        assert pm.date_from_existing("2024_07_20 Mansfield, MA") == "2024-07-20"

    def test_with_dash_separator(self):
        assert pm.date_from_existing(
            "1995-06-19 - Deer Creek Music Center, Noblesville, IN"
        ) == "1995-06-19"

    def test_single_digit_day(self):
        assert pm.date_from_existing("1994_12_6 Goleta, CA") == "1994-12-06"

    def test_legacy_m_dd_yyyy(self):
        assert pm.date_from_existing("7_13_1994 Big Birch Concert Theatre") == "1994-07-13"

    def test_no_match_returns_none(self):
        assert pm.date_from_existing("Live Bait Vol 10") is None

    def test_legacy_m_dd_yyyy_dash_not_supported(self):
        # legacy format only supports underscore separators, not dashes
        assert pm.date_from_existing("7-13-1994 Big Birch Concert Theatre") is None


class TestDateFromTorrent:
    def test_standard_format(self):
        assert pm.date_from_torrent(
            "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"
        ) == "2024-07-20"

    def test_no_phish_prefix(self):
        assert pm.date_from_torrent("2024-07-20.Xfinity.Center") is None

    def test_studio_album_no_match(self):
        assert pm.date_from_torrent("Phish-Farmhouse.[439]") is None


class TestLoad:
    def test_splits_dated_and_undated(self, tmp_path):
        (tmp_path / "2024_07_20 Mansfield, MA").mkdir()
        (tmp_path / "2009-11-27 Albany, NY").mkdir()
        (tmp_path / "Live Bait Vol 10").mkdir()

        dated, undated = pm.load(tmp_path, pm.date_from_existing)

        assert "2024-07-20" in dated
        assert "2009-11-27" in dated
        assert "Live Bait Vol 10" in undated

    def test_skips_dotfiles(self, tmp_path):
        (tmp_path / ".DS_Store").mkdir()
        (tmp_path / "2024_07_20 Mansfield, MA").mkdir()

        dated, undated = pm.load(tmp_path, pm.date_from_existing)

        assert len(dated) == 1
        assert len(undated) == 0

    def test_skips_plain_files(self, tmp_path):
        (tmp_path / "2024_07_20 Mansfield, MA").mkdir()
        (tmp_path / "README.txt").write_text("notes")  # plain file, not a dir

        dated, undated = pm.load(tmp_path, pm.date_from_existing)

        assert len(dated) == 1
        assert len(undated) == 0

    def test_missing_path_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pm.load(tmp_path / "nonexistent", pm.date_from_existing)


class TestExistingToTorrentName:
    def test_simple_city_state(self):
        assert pm.existing_to_torrent_name(
            "2009-11-27 Albany, NY", "2009-11-27"
        ) == "Phish-2009-11-27.Albany.NY"

    def test_with_dash_separator(self):
        assert pm.existing_to_torrent_name(
            "1995-06-19 - Deer Creek Music Center, Noblesville, IN", "1995-06-19"
        ) == "Phish-1995-06-19.Deer.Creek.Music.Center.Noblesville.IN"

    def test_underscore_date(self):
        assert pm.existing_to_torrent_name(
            "2024_07_20 Mansfield, MA", "2024-07-20"
        ) == "Phish-2024-07-20.Mansfield.MA"

    def test_single_digit_day(self):
        assert pm.existing_to_torrent_name(
            "1994_12_6 Goleta, CA", "1994-12-06"
        ) == "Phish-1994-12-06.Goleta.CA"

    def test_legacy_m_dd_yyyy(self):
        assert pm.existing_to_torrent_name(
            "7_13_1994 Big Birch Concert Theatre, Patterson, NY", "1994-07-13"
        ) == "Phish-1994-07-13.Big.Birch.Concert.Theatre.Patterson.NY"
