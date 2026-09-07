"""Load onezeroone submodules without executing package __init__.py (bpy)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Stubs before any submodule import. unittest does not load conftest.py.
if "bpy" not in sys.modules:
    bpy = types.ModuleType("bpy")
    bpy.data = types.SimpleNamespace()
    sys.modules["bpy"] = bpy

if "serial" not in sys.modules:
    serial = types.ModuleType("serial")
    serial.Serial = object
    tools = types.ModuleType("serial.tools")
    list_ports = types.ModuleType("serial.tools.list_ports")
    list_ports.comports = lambda: []
    serial.tools = tools
    sys.modules["serial"] = serial
    sys.modules["serial.tools"] = tools
    sys.modules["serial.tools.list_ports"] = list_ports

ROOT = Path(__file__).resolve().parents[1] / "onezeroone"


def _ensure_package() -> None:
    if "onezeroone" in sys.modules and getattr(sys.modules["onezeroone"], "__path__", None):
        return
    pkg = types.ModuleType("onezeroone")
    pkg.__path__ = [str(ROOT)]
    pkg.__package__ = "onezeroone"
    sys.modules["onezeroone"] = pkg


def load(sub: str):
    """Load ``onezeroone/{sub}.py`` as ``onezeroone.{sub}`` without bpy."""
    _ensure_package()
    name = f"onezeroone.{sub}"
    if name in sys.modules and hasattr(sys.modules[name], "__file__"):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        ROOT / f"{sub}.py",
        submodule_search_locations=[str(ROOT)],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "onezeroone"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
