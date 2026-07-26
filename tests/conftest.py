import sys
from pathlib import Path

# The reference script is standalone tooling (not part of the package);
# tests reach it via path, sharing only the quality table with any future
# implementation (DESIGN §11).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "reference"))
