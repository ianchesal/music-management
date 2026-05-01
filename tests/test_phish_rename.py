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
