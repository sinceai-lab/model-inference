"""Live season backend: FIWARE NGSI-LD notifications in, yield estimates out. See docs/CB_INTEGRATION.md."""
import sys
from pathlib import Path

# The pipeline's modules, and the classes pickled in cache/models.pkl, are imported by their bare names.
SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
