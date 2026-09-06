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


class TestZipCommonTopLevel:
    def test_single_top_level_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/one.flac", "Show/two.flac"])
        assert pi.zip_common_top_level(z) == "Show"

    def test_loose_files_have_no_common_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["one.flac", "two.flac"])
        assert pi.zip_common_top_level(z) is None

    def test_two_top_level_dirs_have_no_common_dir(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/one.flac", "Other/two.flac"])
        assert pi.zip_common_top_level(z) is None

    def test_explicit_empty_dir_entry_only(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Show/"])
        assert pi.zip_common_top_level(z) == "Show"


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


class TestExtractZip:
    def test_extracts_common_dir_as_is(self, tmp_path):
        z = make_zip(tmp_path / "a.zip", ["Phish-2026-07-12.Venue/one.flac"])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_zip(z, collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()

    def test_extracts_loose_files_into_derived_dir(self, tmp_path):
        z = make_zip(tmp_path / "Phish-2026-07-12.Venue.zip", ["one.flac"])
        collection = tmp_path / "collection"
        collection.mkdir()
        pi.extract_zip(z, collection, "Phish-2026-07-12.Venue")
        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()


class TestFindZips:
    def test_returns_sorted_zip_files_only(self, tmp_path):
        (tmp_path / "b.zip").write_bytes(b"")
        (tmp_path / "a.zip").write_bytes(b"")
        (tmp_path / "notes.txt").write_bytes(b"")
        assert [p.name for p in pi.find_zips(tmp_path)] == ["a.zip", "b.zip"]


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


class TestIntakeZips:
    def test_extracts_valid_zip_and_skips_dateless_one(self, tmp_path, capsys):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        make_zip(zips_dir / "Phish-2026-07-12.Venue.zip", ["one.flac"])
        make_zip(zips_dir / "no-date.zip", ["two.flac"])

        results = pi.intake_zips(zips_dir, collection)

        assert (collection / "Phish-2026-07-12.Venue" / "one.flac").exists()
        actions = {r.zip_path.name: r.plan.action for r in results}
        assert actions["Phish-2026-07-12.Venue.zip"] == "extract"
        assert actions["no-date.zip"] == "skip_no_date"

    def test_second_zip_for_same_date_in_same_batch_is_skipped(self, tmp_path):
        zips_dir = tmp_path / "zips"
        zips_dir.mkdir()
        collection = tmp_path / "collection"
        collection.mkdir()
        make_zip(zips_dir / "a-2026-07-12.zip", ["Phish-2026-07-12.Venue/one.flac"])
        make_zip(zips_dir / "b-2026-07-12.zip", ["Phish-2026-07-12.Venue.Dupe/two.flac"])

        results = pi.intake_zips(zips_dir, collection)

        actions = {r.zip_path.name: r.plan.action for r in results}
        assert actions["a-2026-07-12.zip"] == "extract"
        assert actions["b-2026-07-12.zip"] == "skip_exists"
