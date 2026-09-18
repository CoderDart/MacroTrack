import sys
from pathlib import Path
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("src.api.app:app", host=HOST, port=PORT, reload=True)
