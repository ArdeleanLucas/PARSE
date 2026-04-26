"""Root import shim for PARSE Python ai package.

Allows commands run from the repository root, such as:
    python -c "import ai.chat_tools"

without requiring callers to set PYTHONPATH=python first.
"""

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
_python_ai = Path(__file__).resolve().parent.parent / "python" / "ai"
if _python_ai.is_dir():
    __path__.append(str(_python_ai))
