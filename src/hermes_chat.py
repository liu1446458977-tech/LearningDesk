"""Wrapper to run hermes chat with proper session resume.

Patches prompt_toolkit to avoid NoConsoleScreenBufferError
when running hermes CLI as a subprocess (no real Win32 console).
"""
import sys
import os

# Patch prompt_toolkit BEFORE importing hermes_cli
try:
    import prompt_toolkit.output.defaults as _pt_defaults
    _orig_create = _pt_defaults.create_output

    def _safe_create(**kw):
        try:
            return _orig_create(**kw)
        except Exception:
            from prompt_toolkit.output.vt100 import Vt100_Output
            return Vt100_Output(sys.stdout or open(os.devnull, "w"), lambda: 120)

    _pt_defaults.create_output = _safe_create
except ImportError:
    pass

# Ensure hermes_cli is importable
site_pkgs = os.path.join(
    os.environ.get("APPDATA", ""),
    "Python", "Python314", "site-packages",
)
if site_pkgs not in sys.path:
    sys.path.insert(0, site_pkgs)

from hermes_cli.main import main

main()
