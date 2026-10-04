import importlib.util
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-intake"
    loader = SourceFileLoader("phish_intake", str(path))
    spec = importlib.util.spec_from_loader("phish_intake", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pi = load_module()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PHISH_COLLECTION_DIR", raising=False)
    monkeypatch.delenv("PHISH_INTAKE_DIR", raising=False)
    monkeypatch.setattr(pi, "_dotenv_path", lambda: tmp_path / "unused.env")


def make_zip(path: Path, names):
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            if name.endswith("/"):
                zf.writestr(name, "")
            else:
                zf.writestr(name, "data")
    return path


class TestArchiveCommonTopLevel:
    def test_single_top_level_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/one.flac", "Show/two.flac"])
        assert pi.archive_common_top_level(z) == "Show"

    def test_loose_files_have_no_common_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["one.flac", "two.flac"])
        assert pi.archive_common_top_level(z) is None

    def test_two_top_level_dirs_have_no_common_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/one.flac", "Other/two.flac"])
        assert pi.archive_common_top_level(z) is None

    def test_explicit_empty_dir_entry_only(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/"])
        assert pi.archive_common_top_level(z) == "Show"


class TestDateFromDirname:
    def test_dashed_date(self):
        assert pi.date_from_dirname("Phish-2026-07-12.Some.Venue.[123]") == "2026-07-12"

    def test_dotted_date(self):
        assert pi.date_from_dirname("2026.07.12 Some Venue") == "2026-07-12"

    def test_no_date(self):
        assert pi.date_from_dirname("Some Venue No Date") is None


class TestPlanExtraction:
    def test_common_dir_with_date_plans_extract(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Phish-2026-07-12.Venue/one.flac"])
        plan = pi.plan_extraction(z, existing_dirnames=set(), existing_dates=set())
        assert plan.action == "extract"
        assert plan.target_dirname == "Phish-2026-07-12.Venue"

    def test_loose_files_use_zip_stem_as_target(self, tmp_path):
        z = make_zip(tmp_path / "Phish-2026-07-12.Venue.zip", ["one.flac", "two.flac"])
        plan = pi.plan_extraction(z, existing_dirnames=set(), existing_dates=set())
        assert plan.action == "extract"
        assert plan.target_dirname == "Phish-2026-07-12.Venue"

    def test_no_date_anywhere_skips(self, tmp_path):
        z = make_zip(tmp_path / "random.zip", ["one.flac"])
        plan = pi.plan_extraction(z, existing_dirnames=set(), existing_dates=set())
        assert plan.action == "skip_no_date"

    def test_existing_dirname_collision_skips(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Phish-2026-07-12.Venue/one.flac"])
        plan = pi.plan_extraction(
            z, existing_dirnames={"Phish-2026-07-12.Venue"}, existing_dates=set()
        )
        assert plan.action == "skip_exists"

    def test_existing_date_under_different_name_skips(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Phish-2026-07-12.Venue/one.flac"])
        plan = pi.plan_extraction(
            z, existing_dirnames=set(), existing_dates={"2026-07-12"}
        )
        assert plan.action == "skip_exists"


class TestExtractArchive:
    def test_extracts_common_dir_as_is(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Phish-2026-07-12.Venue/one.flac"])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_archive(z, collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()

    def test_extracts_loose_files_into_derived_dir(self, tmp_path):
        z = make_zip(tmp_path / "Phish-2026-07-12.Venue.zip", ["one.flac"])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_archive(z, collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()


class TestFindArchives:
    def test_returns_sorted_zip_files_only(self, tmp_path):
        (tmp_path / "b.zip").write_bytes(b"")
        (tmp_path / "a.zip").write_bytes(b"")
        (tmp_path / "notes.txt").write_bytes(b"")
        assert [p.name for p in pi.find_archives(tmp_path)] == ["a.zip", "b.zip"]


class TestCollectionScan:
    def test_collection_dirnames_lists_only_directories(self, tmp_path):
        (tmp_path / "ShowA").mkdir()
        (tmp_path / "file.txt").write_bytes(b"")
        assert pi.collection_dirnames(tmp_path) == {"ShowA"}

    def test_collection_dates_extracts_dates_from_names(self):
        dirnames = {"Phish-2026-07-12.Venue.[1]", "no-date-here"}
        assert pi.collection_dates(dirnames) == {"2026-07-12"}


class TestConfirm:
    def test_yes_input_returns_true(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "y")
        assert pi.confirm("proceed?") is True

    def test_no_input_returns_false(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        assert pi.confirm("proceed?") is False

    def test_empty_input_returns_false(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *_: "")
        assert pi.confirm("proceed?") is False


class TestRunTool:
    def test_dry_run_invokes_script_without_execute_flag(self, monkeypatch, tmp_path):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(pi.subprocess, "run", mock_run)
        pi.run_tool("phish-rename", tmp_path, execute=False)
        args = mock_run.call_args.args[0]
        assert args[-2:] == [str(tmp_path)] or str(tmp_path) in args
        assert "--execute" not in args

    def test_execute_invokes_script_with_execute_flag(self, monkeypatch, tmp_path):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(pi.subprocess, "run", mock_run)
        pi.run_tool("phish-rename", tmp_path, execute=True)
        args = mock_run.call_args.args[0]
        assert "--execute" in args

    def test_script_path_resolves_next_to_phish_intake(self, monkeypatch, tmp_path):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(pi.subprocess, "run", mock_run)
        pi.run_tool("phish-retag", tmp_path, execute=False)
        args = mock_run.call_args.args[0]
        script_arg = Path(args[1])
        assert script_arg.name == "phish-retag"
        assert script_arg.parent == Path(pi.__file__).resolve().parent


class TestParseArgs:
    def test_defaults_from_env_vars(self, monkeypatch, tmp_path):
        zipdir = tmp_path / "zips"
        collection = tmp_path / "collection"
        monkeypatch.setenv("PHISH_INTAKE_DIR", str(zipdir))
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(collection))
        zips_dir, collection_dir, auto_yes = pi.parse_args(["phish-intake"])
        assert zips_dir == zipdir
        assert collection_dir == collection
        assert auto_yes is False

    def test_positional_zipdir_overrides_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_INTAKE_DIR", str(tmp_path / "envzips"))
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path / "col"))
        explicit = tmp_path / "explicit"
        zips_dir, *_ = pi.parse_args(["phish-intake", str(explicit)])
        assert zips_dir == explicit

    def test_collection_flag_overrides_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path / "envcol"))
        explicit = tmp_path / "explicit-col"
        _, collection_dir, _ = pi.parse_args(
            ["phish-intake", str(tmp_path), "--collection", str(explicit)]
        )
        assert collection_dir == explicit

    def test_yes_flag(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path / "col"))
        _, _, auto_yes = pi.parse_args(["phish-intake", str(tmp_path), "--yes"])
        assert auto_yes is True

    def test_missing_zipdir_and_no_env_var_exits(self):
        with pytest.raises(SystemExit):
            pi.parse_args(["phish-intake"])

    def test_missing_collection_and_no_env_var_exits(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_INTAKE_DIR", str(tmp_path))
        with pytest.raises(SystemExit):
            pi.parse_args(["phish-intake"])


class TestIntakeArchives:
    def test_extracts_valid_zip_and_skips_dateless_one(self, tmp_path, capsys):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        make_zip(zips_dir / "Phish-2026-07-12.Venue.zip", ["one.flac"])
        make_zip(zips_dir / "no-date.zip", ["two.flac"])

        results = pi.intake_archives(zips_dir, collection)

        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()
        actions = {r.archive_path.name: r.plan.action for r in results}
        assert actions["Phish-2026-07-12.Venue.zip"] == "extract"
        assert actions["no-date.zip"] == "skip_no_date"

    def test_second_zip_for_same_date_in_same_batch_is_skipped(self, tmp_path):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        make_zip(zips_dir / "a-2026-07-12.zip", ["Phish-2026-07-12.Venue/one.flac"])
        make_zip(zips_dir / "b-2026-07-12.zip", ["Phish-2026-07-12.Venue.Dupe/two.flac"])

        results = pi.intake_archives(zips_dir, collection)

        actions = {r.archive_path.name: r.plan.action for r in results}
        assert actions["a-2026-07-12.zip"] == "extract"
        assert actions["b-2026-07-12.zip"] == "skip_exists"


# ── RAR support ────────────────────────────────────────────────────────────────

class FakeUnrar:
    """Stands in for the unrar binary: `vt` prints a technical listing of the
    configured entries, `x` writes them under the destination directory."""

    def __init__(self, entries, fail_extract=False):
        self.entries = entries  # list of (name, is_dir)
        self.fail_extract = fail_extract
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "vt":
            lines = ["", "UNRAR 7.12 freeware", "", f"Archive: {args[-1]}", "Details: RAR 5", ""]
            for name, is_dir in self.entries:
                lines += [f"        Name: {name}", f"        Type: {'Directory' if is_dir else 'File'}", ""]
            return MagicMock(returncode=0, stdout="\n".join(lines), stderr="")
        if args[0] == "x":
            if self.fail_extract:
                return MagicMock(returncode=3, stdout="", stderr="CRC failed")
            dest = Path(args[-1])
            for name, is_dir in self.entries:
                target = dest / name
                if is_dir:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("data")
            return MagicMock(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected unrar call {args}")


@pytest.fixture
def fake_unrar(monkeypatch):
    def install(entries, fail_extract=False):
        fake = FakeUnrar(entries, fail_extract)
        monkeypatch.setattr(pi, "_unrar", fake)
        monkeypatch.setattr(pi, "unrar_available", lambda: True)
        return fake
    return install


class TestRarCommonTopLevel:
    def test_single_top_level_dir(self, tmp_path, fake_unrar):
        fake_unrar([("Show", True), ("Show/one.flac", False)])
        assert pi.archive_common_top_level(tmp_path / "a.rar") == "Show"

    def test_dir_entry_only(self, tmp_path, fake_unrar):
        fake_unrar([("Show", True)])
        assert pi.archive_common_top_level(tmp_path / "a.rar") == "Show"

    def test_loose_files_have_no_common_dir(self, tmp_path, fake_unrar):
        fake_unrar([("one.flac", False), ("two.flac", False)])
        assert pi.archive_common_top_level(tmp_path / "a.rar") is None

    def test_two_top_level_dirs_have_no_common_dir(self, tmp_path, fake_unrar):
        fake_unrar([("Show/one.flac", False), ("Other/two.flac", False)])
        assert pi.archive_common_top_level(tmp_path / "a.rar") is None


class TestRarExtraction:
    def test_extracts_common_dir_as_is(self, tmp_path, fake_unrar):
        fake_unrar([("Phish-2026-07-12.Venue/one.flac", False)])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_archive(tmp_path / "a.rar", collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()

    def test_extracts_loose_files_into_derived_dir(self, tmp_path, fake_unrar):
        fake = fake_unrar([("one.flac", False)])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_archive(tmp_path / "Phish-2026-07-12.Venue.rar", collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()
        extract_call = [c for c in fake.calls if c[0] == "x"][0]
        assert "-o-" in extract_call  # never overwrite

    def test_failed_extraction_raises(self, tmp_path, fake_unrar):
        fake_unrar([("one.flac", False)], fail_extract=True)
        collection = tmp_path / "collection"
        collection.mkdir()
        with pytest.raises(pi.ExtractionError, match="CRC failed"):
            pi.extract_archive(tmp_path / "Phish-2026-07-12.Venue.rar", collection, "Phish-2026-07-12.Venue")


class TestRarPlanExtraction:
    def test_multipart_target_drops_part_suffix(self, tmp_path, fake_unrar):
        fake_unrar([("one.flac", False)])
        plan = pi.plan_extraction(
            tmp_path / "Phish-2026-07-12.Venue.part1.rar", existing_dirnames=set(), existing_dates=set()
        )
        assert plan.action == "extract"
        assert plan.target_dirname == "Phish-2026-07-12.Venue"

    def test_skips_when_unrar_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pi, "unrar_available", lambda: False)
        plan = pi.plan_extraction(
            tmp_path / "Phish-2026-07-12.Venue.rar", existing_dirnames=set(), existing_dates=set()
        )
        assert plan.action == "skip_no_unrar"


class TestFindArchivesRar:
    def test_includes_rar_and_only_first_multipart_volume(self, tmp_path):
        for name in [
            "a.zip", "b.rar", "b.r00", "b.r01",
            "c.part1.rar", "c.part2.rar",
            "d.part01.rar", "d.part02.rar", "d.part10.rar",
            "notes.txt",
        ]:
            (tmp_path / name).write_bytes(b"")
        assert [p.name for p in pi.find_archives(tmp_path)] == [
            "a.zip", "b.rar", "c.part1.rar", "d.part01.rar",
        ]


class TestArchiveVolumes:
    def test_zip_is_single_volume(self, tmp_path):
        z = tmp_path / "a.zip"
        z.write_bytes(b"")
        assert pi.archive_volumes(z) == [z]

    def test_old_style_rar_volumes(self, tmp_path):
        for name in ["b.rar", "b.r00", "b.r01", "bb.r00"]:
            (tmp_path / name).write_bytes(b"")
        assert [p.name for p in pi.archive_volumes(tmp_path / "b.rar")] == ["b.rar", "b.r00", "b.r01"]

    def test_new_style_rar_volumes(self, tmp_path):
        for name in ["c.part01.rar", "c.part02.rar", "c.part10.rar", "cc.part02.rar"]:
            (tmp_path / name).write_bytes(b"")
        assert [p.name for p in pi.archive_volumes(tmp_path / "c.part01.rar")] == [
            "c.part01.rar", "c.part02.rar", "c.part10.rar",
        ]


class TestIntakeArchivesRar:
    def test_extracts_rar_alongside_zip(self, tmp_path, fake_unrar):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        make_zip(zips_dir / "Phish-2026-07-12.Venue.zip", ["one.flac"])
        (zips_dir / "Phish-2026-07-14.Other.rar").write_bytes(b"")
        fake_unrar([("two.flac", False)])

        results = pi.intake_archives(zips_dir, collection)

        actions = {r.archive_path.name: r.plan.action for r in results}
        assert actions == {
            "Phish-2026-07-12.Venue.zip": "extract",
            "Phish-2026-07-14.Other.rar": "extract",
        }
        assert (collection / "Phish-2026-07-14.Other" / "two.flac").exists()

    def test_failed_extraction_is_reported_and_batch_continues(self, tmp_path, fake_unrar, capsys):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        (zips_dir / "Phish-2026-07-12.Venue.rar").write_bytes(b"")
        make_zip(zips_dir / "Phish-2026-07-14.Other.zip", ["one.flac"])
        fake_unrar([("two.flac", False)], fail_extract=True)

        results = pi.intake_archives(zips_dir, collection)

        actions = {r.archive_path.name: r.plan.action for r in results}
        assert actions["Phish-2026-07-12.Venue.rar"] == "error"
        assert actions["Phish-2026-07-14.Other.zip"] == "extract"
        assert "FAILED" in capsys.readouterr().out
