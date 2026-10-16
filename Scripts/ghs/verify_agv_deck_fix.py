import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from agv_deck_fix import verify
if __name__=='__main__': verify()
