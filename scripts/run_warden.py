"""PyInstaller entry point. ``python -m warden`` works fine for a normal
install; PyInstaller needs an actual script file to point at, so this is
just that, kept to one line of real logic on purpose.
"""

import sys

from warden.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
