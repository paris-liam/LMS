import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("create")
