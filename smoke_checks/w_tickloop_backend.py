"""Regression (Mac port): TickLoop gets its window backend from make_window_backend(),
not a hardcoded Win32Windows() that raised on a Mac."""

import inspect

from _util import check, run


def main():
    from warden.core import tick

    src = inspect.getsource(tick.TickLoop.__init__)
    check("TickLoop uses make_window_backend()", "make_window_backend()" in src)
    check("no hardcoded Win32Windows() in TickLoop", "window_backend = Win32Windows()" not in src)
    from warden.platform import window

    check("Windows still gets Win32Windows",
          "return Win32Windows()" in inspect.getsource(window.make_window_backend))


run(main)
