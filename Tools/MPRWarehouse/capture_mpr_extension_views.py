"""Native game-view comparison and inspection of all extension directions."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_reference_runtime_views as capture
capture.OUT=capture.ROOT/'Saved/MPR/extension_20261104/runtime_views'
capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[
 ('01-main-preserved',[0,0,8],75000,-52,-90,False),
 ('02-extension-overall',[0,150,0],165000,-65,-90,False),
 ('03-north-extension',[-100,575,0],72000,-55,-85,False),
 ('04-west-extension',[-560,0,0],65000,-52,-130,False),
 ('05-south-extension',[0,-460,0],70000,-55,-65,False),
 ('06-north-junctions',[-190,355,0],50000,-66,-90,False),
 ('07-west-junctions',[-460,30,0],50000,-65,-90,False),
 ('08-rail-extension',[430,520,0],65000,-50,-65,False),
 ('09-south-junctions',[-50,-300,0],55000,-65,-90,False),
 ('10-interior-preserved',[0,0,4],49000,-60,-90,True),
 ('11-southwest-corner-detail',[-455,-310,0],22000,-62,-90,False),
 ('12-west-dense-mouths',[-480,-190,0],20000,-62,-90,False),
 ('13-south-rail-and-crossings',[-100,-465,0],18000,-55,-60,False),
 ('14-crossing-height-detail',[-94,-443,0],4500,-28,-60,False),
]
