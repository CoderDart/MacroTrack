import sys
from pathlib import Path
import subprocess

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if __name__ == "__main__":
    target = ROOT_DIR / "src" / "ui" / "dashboard.py"
    subprocess.run(["streamlit", "run", str(target)], check=True)
