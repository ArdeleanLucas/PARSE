"""Root import shim for PARSE Python adapters.

Allows commands run from the repository root, such as:
    python -c "import adapters.mcp_adapter"

without requiring callers to set PYTHONPATH=python first.
"""

from pkgutil import extend_path
from pathlib import Path

__path__ = extend_path(__path__, __name__)
_python_adapters = Path(__file__).resolve().parent.parent / "python" / "adapters"
if _python_adapters.is_dir():
    __path__.append(str(_python_adapters))
