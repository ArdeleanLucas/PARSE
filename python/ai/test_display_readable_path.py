import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools


def test_display_readable_path_normalizes_project_relative_windows_paths_to_posix(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)
    tools.project_root = pathlib.PureWindowsPath("C:/proj")

    path = pathlib.PureWindowsPath("C:/proj/audio/working/Fail02/speaker.wav")

    assert tools._display_readable_path(path) == "audio/working/Fail02/speaker.wav"
