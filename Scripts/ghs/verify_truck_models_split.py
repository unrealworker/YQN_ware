"""Fresh editor-process verification of the independent truck placements."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_dock_truck_models import verify

if __name__ == '__main__':
    from cad_rack_revision_state import dispatch_agv_deck_verification
    if not dispatch_agv_deck_verification():
        verify()
