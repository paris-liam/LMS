import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402


class handler(make_handler("add_copy")):  # a class statement: Vercel finds handlers by reading the source
    pass
