"""
Python-interpreter resolution that survives PyInstaller freezing.

Inside a frozen sidecar binary, ``sys.executable`` is the sidecar launcher
itself — re-invoking it with a script path would relaunch swadb with the
script as CLI arguments and silently misbehave. Skill execution in packaged
mode therefore needs a real system Python (or a clear error when none
exists).
"""
import shutil
import sys


def is_frozen():
    """True when running inside a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


def python_interpreter():
    """
    Path to a real Python interpreter for running skill scripts.

    Returns ``sys.executable`` in a normal install, a system ``python3``/
    ``python`` from PATH in a frozen bundle, or None when frozen with no
    system Python available (callers should surface a readable error).
    """
    if not is_frozen():
        return sys.executable
    return shutil.which("python3") or shutil.which("python")


NO_PYTHON_ERROR = (
    "Python skill execution is unavailable in the packaged sidecar: no "
    "system 'python3' or 'python' was found on PATH. Install Python to "
    "enable Python skills; bash skills are unaffected."
)
