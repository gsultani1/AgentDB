"""Allow ``python -m swadb`` to invoke the CLI.

The console-script entry point installed by pip (``swadb``) and this
module form are equivalent — both call :func:`swadb.cli.main`. This
exists so that users who reach for ``python -m swadb`` (the natural
first guess, especially when the Scripts directory isn't on PATH) get
the CLI instead of a ``No module named swadb.__main__`` error.
"""

from swadb.cli import main


if __name__ == "__main__":
    main()
