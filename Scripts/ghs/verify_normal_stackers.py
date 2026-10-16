import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import add_normal_stackers
from cad_rack_revision_state import dispatch_normal_stacker_fx_verification
if not dispatch_normal_stacker_fx_verification():
    add_normal_stackers.verify()
