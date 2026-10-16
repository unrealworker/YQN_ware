"""Apply independent truck placements after the live editor has saved and exited."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_dock_truck_models import run
run(headless=True)
