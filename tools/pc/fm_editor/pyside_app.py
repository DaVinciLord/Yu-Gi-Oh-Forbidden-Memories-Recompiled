"""The Qt FM Editor.

The window itself is `qt/window.py` and a page's own code is a module beside
it (`qt/packs.py`, `qt/map.py`, ...), as the Tk editor is split into
`tabs.py`, `packs_tab.py` and the rest. This module is the name the rest of
the editor and the tests know them by.
"""
from __future__ import annotations

from .qt.common import *          # noqa: F401,F403
from .qt.common import (_qimage, _line_count, _pairs_text, _parse_pairs, _whole,
                        _card_image)      # noqa: F401
from .qt.window import ModernEditor, main      # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
