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


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PHISH_COLLECTION_DIR", raising=False)
    monkeypatch.delenv("PHISH_INTAKE_DIR", raising=False)
    monkeypatch.setattr(pm, "_dotenv_path", lambda: tmp_path / "unused.env")


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


class TestPreflight:
    def test_missing_existing_path_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pm.preflight(tmp_path / "nonexistent", tmp_path, None, execute=False)

    def test_missing_torrent_path_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pm.preflight(tmp_path, tmp_path / "nonexistent", None, execute=False)

    def test_execute_without_nas_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pm.preflight(tmp_path, tmp_path, None, execute=True)

    def test_execute_with_missing_nas_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pm.preflight(tmp_path, tmp_path, tmp_path / "nonexistent", execute=True)

    def test_valid_dry_run_does_not_exit(self, tmp_path):
        pm.preflight(tmp_path, tmp_path, None, execute=False)  # must not raise

    def test_valid_execute_does_not_exit(self, tmp_path):
        nas = tmp_path / "nas"
        nas.mkdir()
        pm.preflight(tmp_path, tmp_path, nas, execute=True)  # must not raise


class TestParseArgsPhase:
    def test_no_phase_returns_none(self):
        _, _, _, _, phase = pm.parse_args(["phish-merge"])
        assert phase is None

    def test_phase_flag_returns_integer(self):
        _, _, _, _, phase = pm.parse_args(["phish-merge", "--phase", "2"])
        assert phase == 2

    def test_phase_one_accepted(self):
        _, _, _, _, phase = pm.parse_args(["phish-merge", "--phase", "1"])
        assert phase == 1

    def test_phase_four_accepted(self):
        _, _, _, _, phase = pm.parse_args(["phish-merge", "--phase", "4"])
        assert phase == 4

    def test_phase_zero_exits(self):
        with pytest.raises(SystemExit):
            pm.parse_args(["phish-merge", "--phase", "0"])

    def test_phase_five_exits(self):
        with pytest.raises(SystemExit):
            pm.parse_args(["phish-merge", "--phase", "5"])

    def test_phase_non_integer_exits(self):
        with pytest.raises(SystemExit):
            pm.parse_args(["phish-merge", "--phase", "backup"])

    def test_missing_phase_value_exits(self):
        with pytest.raises(SystemExit):
            pm.parse_args(["phish-merge", "--phase"])


class TestEnvVarDefaults:
    def test_no_env_var_falls_back_to_hardcoded_defaults(self):
        existing_path, torrent_path, *_ = pm.parse_args(["phish-merge"])
        assert existing_path == pm.DEFAULT_EXISTING
        assert torrent_path == pm.DEFAULT_TORRENT

    def test_collection_env_var_sets_existing_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path))
        existing_path, *_ = pm.parse_args(["phish-merge"])
        assert existing_path == tmp_path

    def test_intake_env_var_sets_torrent_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_INTAKE_DIR", str(tmp_path))
        _, torrent_path, *_ = pm.parse_args(["phish-merge"])
        assert torrent_path == tmp_path

    def test_explicit_flag_overrides_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path))
        other = tmp_path / "other"
        other.mkdir()
        existing_path, *_ = pm.parse_args(["phish-merge", "--existing", str(other)])
        assert existing_path == other

    def test_dotenv_file_used_when_no_real_env_var(self, monkeypatch, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text(f"PHISH_COLLECTION_DIR={tmp_path}\nPHISH_INTAKE_DIR={tmp_path}\n")
        monkeypatch.setattr(pm, "_dotenv_path", lambda: dotenv)
        existing_path, torrent_path, *_ = pm.parse_args(["phish-merge"])
        assert existing_path == tmp_path
        assert torrent_path == tmp_path


from unittest.mock import patch


class TestPhaseBackup:
    def test_dry_run_with_nas_prints_rsync_command(self, tmp_path, capsys):
        existing = tmp_path / "existing"
        existing.mkdir()
        nas = tmp_path / "nas"

        pm.phase_backup(existing, nas, dry_run=True)

        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "DRY RUN" in out
        assert "rsync" in out
        assert str(existing) in out

    def test_dry_run_with_none_nas_prints_placeholder(self, tmp_path, capsys):
        existing = tmp_path / "existing"
        existing.mkdir()

        pm.phase_backup(existing, None, dry_run=True)

        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "DRY RUN" in out

    def test_execute_calls_rsync(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        nas = tmp_path / "nas"
        nas.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            pm.phase_backup(existing, nas, dry_run=False)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "rsync" in cmd
        assert f"{existing}/" in cmd
        assert str(nas) in cmd

    def test_execute_exits_on_rsync_failure(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        nas = tmp_path / "nas"
        nas.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            with pytest.raises(SystemExit):
                pm.phase_backup(existing, nas, dry_run=False)


class TestPhaseCopyNew:
    def _make_show(self, parent, dirname):
        show = parent / dirname
        show.mkdir(parents=True)
        (show / "track01.flac").write_text("audio")

    def test_dry_run_prints_and_touches_nothing(self, tmp_path, capsys):
        torrent  = tmp_path / "torrent"
        existing = tmp_path / "existing"
        existing.mkdir()
        self._make_show(torrent, "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]")

        tr_dated = {"2024-07-20": ["Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"]}
        pm.phase_copy_new(torrent, existing, ["2024-07-20"], tr_dated, dry_run=True)

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "Phish-2024-07-20" in out
        assert not (existing / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]").exists()

    def test_execute_copies_directory(self, tmp_path):
        torrent  = tmp_path / "torrent"
        existing = tmp_path / "existing"
        existing.mkdir()
        self._make_show(torrent, "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]")

        tr_dated = {"2024-07-20": ["Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"]}
        count = pm.phase_copy_new(torrent, existing, ["2024-07-20"], tr_dated, dry_run=False)

        assert count == 1
        assert (existing / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]" / "track01.flac").exists()

    def test_skips_if_destination_exists(self, tmp_path, capsys):
        torrent  = tmp_path / "torrent"
        existing = tmp_path / "existing"
        existing.mkdir()
        dirname = "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"
        self._make_show(torrent, dirname)
        (existing / dirname).mkdir()  # already present

        tr_dated = {"2024-07-20": [dirname]}
        count = pm.phase_copy_new(torrent, existing, ["2024-07-20"], tr_dated, dry_run=False)

        assert count == 0
        assert "SKIP" in capsys.readouterr().out


class TestPhaseReplaceMatched:
    def _setup(self, tmp_path):
        torrent  = tmp_path / "torrent"
        existing = tmp_path / "existing"
        existing.mkdir()
        tr_dir = "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]"
        ex_dir = "2009-11-27 Albany, NY"
        tr_show = torrent / tr_dir
        tr_show.mkdir(parents=True)
        (tr_show / "track01.flac").write_text("flac")
        ex_show = existing / ex_dir
        ex_show.mkdir()
        (ex_show / "track01.mp3").write_text("mp3")
        return torrent, existing, tr_dir, ex_dir

    def test_dry_run_prints_and_touches_nothing(self, tmp_path, capsys):
        torrent, existing, tr_dir, ex_dir = self._setup(tmp_path)
        ex_dated = {"2009-11-27": [ex_dir]}
        tr_dated = {"2009-11-27": [tr_dir]}

        pm.phase_replace_matched(torrent, existing, ["2009-11-27"], ex_dated, tr_dated, dry_run=True)

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert tr_dir in out
        assert (existing / ex_dir).exists()       # nothing deleted
        assert not (existing / tr_dir).exists()   # nothing copied

    def test_execute_copies_torrent_and_removes_old(self, tmp_path):
        torrent, existing, tr_dir, ex_dir = self._setup(tmp_path)
        ex_dated = {"2009-11-27": [ex_dir]}
        tr_dated = {"2009-11-27": [tr_dir]}

        count = pm.phase_replace_matched(
            torrent, existing, ["2009-11-27"], ex_dated, tr_dated, dry_run=False
        )

        assert count == 1
        assert (existing / tr_dir / "track01.flac").exists()
        assert not (existing / ex_dir).exists()

    def test_skips_copy_if_dst_exists_but_still_removes_old(self, tmp_path):
        torrent, existing, tr_dir, ex_dir = self._setup(tmp_path)
        (existing / tr_dir).mkdir()  # destination already exists
        ex_dated = {"2009-11-27": [ex_dir]}
        tr_dated = {"2009-11-27": [tr_dir]}

        pm.phase_replace_matched(
            torrent, existing, ["2009-11-27"], ex_dated, tr_dated, dry_run=False
        )

        assert (existing / tr_dir).exists()
        assert not (existing / ex_dir).exists()

    def test_removes_all_old_dirs_for_date(self, tmp_path):
        torrent, existing, tr_dir, _ = self._setup(tmp_path)
        ex_dir2 = "2009-11-27 Albany NY (alt)"
        (existing / ex_dir2).mkdir()
        ex_dated = {"2009-11-27": ["2009-11-27 Albany, NY", ex_dir2]}
        tr_dated = {"2009-11-27": [tr_dir]}

        pm.phase_replace_matched(
            torrent, existing, ["2009-11-27"], ex_dated, tr_dated, dry_run=False
        )

        assert not (existing / "2009-11-27 Albany, NY").exists()
        assert not (existing / ex_dir2).exists()
        assert (existing / tr_dir).exists()


class TestPhaseRenameExisting:
    def test_dry_run_prints_and_touches_nothing(self, tmp_path, capsys):
        ex_dir = "2009-11-27 Albany, NY"
        (tmp_path / ex_dir).mkdir()
        ex_dated = {"2009-11-27": [ex_dir]}

        pm.phase_rename_existing(tmp_path, ["2009-11-27"], ex_dated, dry_run=True)

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "Phish-2009-11-27.Albany.NY" in out
        assert (tmp_path / ex_dir).exists()  # nothing moved

    def test_execute_renames_directory(self, tmp_path):
        ex_dir = "2009-11-27 Albany, NY"
        (tmp_path / ex_dir).mkdir()
        ex_dated = {"2009-11-27": [ex_dir]}

        count = pm.phase_rename_existing(tmp_path, ["2009-11-27"], ex_dated, dry_run=False)

        assert count == 1
        assert not (tmp_path / ex_dir).exists()
        assert (tmp_path / "Phish-2009-11-27.Albany.NY").exists()

    def test_skips_already_correctly_named(self, tmp_path):
        ex_dir = "Phish-2009-11-27.Albany.NY"
        (tmp_path / ex_dir).mkdir()
        ex_dated = {"2009-11-27": [ex_dir]}

        count = pm.phase_rename_existing(tmp_path, ["2009-11-27"], ex_dated, dry_run=False)

        assert count == 0
        assert (tmp_path / ex_dir).exists()


class TestEndToEnd:
    def _build_collection(self, tmp_path):
        existing = tmp_path / "existing"
        torrent  = tmp_path / "torrent"
        existing.mkdir()
        torrent.mkdir()

        # Matched show: in both collections
        (existing / "2009-11-27 Albany, NY").mkdir()
        tr_matched = torrent / "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]"
        tr_matched.mkdir()
        (tr_matched / "track01.flac").write_text("flac")

        # Torrent-only show
        tr_new = torrent / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"
        tr_new.mkdir()
        (tr_new / "track01.flac").write_text("flac")

        # Existing-only show
        (existing / "1995-06-19 - Deer Creek Music Center, Noblesville, IN").mkdir()

        return existing, torrent

    def test_dry_run_covers_all_phases_and_touches_nothing(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)

        pm.main_logic(existing, torrent, nas_path=None, dry_run=True)

        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "Phase 2" in out
        assert "Phase 3" in out
        assert "Phase 4" in out
        assert "DRY RUN" in out
        # Disk untouched
        assert (existing / "2009-11-27 Albany, NY").exists()
        assert (existing / "1995-06-19 - Deer Creek Music Center, Noblesville, IN").exists()
        assert not (existing / "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]").exists()

    def test_execute_performs_full_merge(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        nas = tmp_path / "nas"
        nas.mkdir()

        from unittest.mock import patch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            pm.main_logic(existing, torrent, nas_path=nas, dry_run=False)

        # Torrent-only show was copied
        assert (existing / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]" / "track01.flac").exists()
        # Matched show: torrent canonical present, old gone
        assert (existing / "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]" / "track01.flac").exists()
        assert not (existing / "2009-11-27 Albany, NY").exists()
        # Existing-only show was renamed
        assert not (existing / "1995-06-19 - Deer Creek Music Center, Noblesville, IN").exists()
        assert (existing / "Phish-1995-06-19.Deer.Creek.Music.Center.Noblesville.IN").exists()


class TestMainLogicPhaseFilter:
    def _build_collection(self, tmp_path):
        existing = tmp_path / "existing"
        torrent  = tmp_path / "torrent"
        existing.mkdir()
        torrent.mkdir()
        (existing / "2009-11-27 Albany, NY").mkdir()
        tr_matched = torrent / "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]"
        tr_matched.mkdir()
        (tr_matched / "track01.flac").write_text("flac")
        tr_new = torrent / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]"
        tr_new.mkdir()
        (tr_new / "track01.flac").write_text("flac")
        (existing / "1995-06-19 - Deer Creek Music Center, Noblesville, IN").mkdir()
        return existing, torrent

    def test_no_phase_runs_all_phases(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=True, phase=None)
        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "Phase 2" in out
        assert "Phase 3" in out
        assert "Phase 4" in out

    def test_phase_1_runs_only_backup(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=True, phase=1)
        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "Phase 2" not in out
        assert "Phase 3" not in out
        assert "Phase 4" not in out

    def test_phase_2_runs_only_copy_new(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=True, phase=2)
        out = capsys.readouterr().out
        assert "Phase 2" in out
        assert "Phase 1" not in out
        assert "Phase 3" not in out
        assert "Phase 4" not in out

    def test_phase_3_runs_only_replace_matched(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=True, phase=3)
        out = capsys.readouterr().out
        assert "Phase 3" in out
        assert "Phase 1" not in out
        assert "Phase 2" not in out
        assert "Phase 4" not in out

    def test_phase_4_runs_only_rename_existing(self, tmp_path, capsys):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=True, phase=4)
        out = capsys.readouterr().out
        assert "Phase 4" in out
        assert "Phase 1" not in out
        assert "Phase 2" not in out
        assert "Phase 3" not in out

    def test_phase_4_execute_only_renames(self, tmp_path):
        existing, torrent = self._build_collection(tmp_path)
        pm.main_logic(existing, torrent, nas_path=None, dry_run=False, phase=4)
        assert (existing / "Phish-1995-06-19.Deer.Creek.Music.Center.Noblesville.IN").exists()
        assert not (existing / "1995-06-19 - Deer Creek Music Center, Noblesville, IN").exists()
        assert not (existing / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]").exists()
        assert (existing / "2009-11-27 Albany, NY").exists()
