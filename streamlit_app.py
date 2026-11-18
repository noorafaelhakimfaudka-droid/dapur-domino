"""Root entrypoint for Streamlit Community Cloud deployment."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from dapur_domino.app.streamlit_app import main  # noqa: E402

if __name__ == "__main__":
    main()
