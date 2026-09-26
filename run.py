"""Run the local WS lethal probability calculator."""

import sys

from ws_tcg.web import serve


if __name__ == "__main__":
    frozen = getattr(sys, "frozen", False)
    no_browser = "--no-browser" in sys.argv
    serve(port=0 if frozen else 8000, open_browser=frozen and not no_browser)
