"""
CLI --version flag: exits 0 and reports the package version.

Runs the CLI as a real subprocess (python -m swadb) rather than calling
main() in-process, so argparse's SystemExit and stdout wiring are exercised
the same way a user's shell would see them.
"""
import subprocess
import sys

from swadb import __version__


def test_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "swadb", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
