"""Checkpoint the accepted CAD rack revision before the next authorized changes."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import backup_cad_rack_revision as backup
backup.REPORT=ROOT/'Saved/GHS_RefinementV2Checkpoint.json'
backup.run()
