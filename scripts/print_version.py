import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import orchsketch  # noqa: E402

print(orchsketch.__version__)
