"""Capture added column edges from the user's current inspection viewpoint."""
from pathlib import Path
source=Path(r'D:\UEPro\Test\Scripts\ghs\capture_wall_detail.py').read_text()
source=source.replace("phase=(ROOT/'Saved/GHS_WallCapturePhase.txt').read_text().strip()","phase='After'")
source=source.replace('GHS_WallEdgeLiveBefore.json','GHS_ColumnOutlineView.json')
source=source.replace('GHS_WallJoints_','GHS_ColumnOutlines_').replace('GHS_WallCapture','GHS_ColumnOutlinesCapture')
exec(compile(source,'capture_column_outlines_impl.py','exec'),globals())
