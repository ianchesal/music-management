import importlib.util
from pathlib import Path

import pytest


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-compare"
    loader = SourceFileLoader("phish_compare", str(path))
    spec = importlib.util.spec_from_loader("phish_compare", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = load_module()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PHISH_COLLECTION_DIR", raising=False)
    monkeypatch.delenv("PHISH_INTAKE_DIR", raising=False)
    monkeypatch.setattr(pc, "_dotenv_path", lambda: tmp_path / "unused.env")


class TestParseArgs:
    def test_no_flags_returns_hardcoded_defaults(self):
        existing_path, torrent_path, studio_path = pc.parse_args(["phish-compare"])
        assert existing_path == pc.DEFAULT_EXISTING
        assert torrent_path == pc.DEFAULT_TORRENT
        assert studio_path == pc.DEFAULT_STUDIO

    def test_explicit_flags_override(self, tmp_path):
        existing_path, torrent_path, studio_path = pc.parse_args(
            ["phish-compare", "--existing", str(tmp_path), "--torrent", str(tmp_path),
             "--studio", str(tmp_path)]
        )
        assert existing_path == tmp_path
        assert torrent_path == tmp_path
        assert studio_path == tmp_path

    def test_unknown_arg_exits(self):
        with pytest.raises(SystemExit):
            pc.parse_args(["phish-compare", "--bogus"])


class TestEnvVarDefaults:
    def test_collection_env_var_sets_existing_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path))
        existing_path, *_ = pc.parse_args(["phish-compare"])
        assert existing_path == tmp_path

    def test_intake_env_var_sets_torrent_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_INTAKE_DIR", str(tmp_path))
        _, torrent_path, _ = pc.parse_args(["phish-compare"])
        assert torrent_path == tmp_path

    def test_explicit_flag_overrides_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PHISH_COLLECTION_DIR", str(tmp_path))
        other = tmp_path / "other"
        other.mkdir()
        existing_path, *_ = pc.parse_args(["phish-compare", "--existing", str(other)])
        assert existing_path == other

    def test_dotenv_file_used_when_no_real_env_var(self, monkeypatch, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text(f"PHISH_COLLECTION_DIR={tmp_path}\nPHISH_INTAKE_DIR={tmp_path}\n")
        monkeypatch.setattr(pc, "_dotenv_path", lambda: dotenv)
        existing_path, torrent_path, _ = pc.parse_args(["phish-compare"])
        assert existing_path == tmp_path
        assert torrent_path == tmp_path
