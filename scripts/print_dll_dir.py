import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from orchsketch.playback.fluid_env import find_dll_dir  # noqa: E402

print(find_dll_dir())
