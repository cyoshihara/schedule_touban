"""pytest 共通設定: src/ を import path に追加する。"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
  sys.path.insert(0, _SRC)
