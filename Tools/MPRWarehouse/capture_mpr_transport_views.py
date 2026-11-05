"""Seven native game frames for the scoped transport patch; never save assets.

VIEWS uses CAD XY metres; the shared capture applies UE's single Y reflection.
Launch a separate 1920x1080 -game -RenderOffscreen process, not the user's editor.
"""
from pathlib import Path
import hashlib,sys
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
base.MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
base.MAP_FILE=base.ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
base.result['map']=base.MAP
import capture_mpr_reference_runtime_views as capture
capture.OUT=base.ROOT/'Saved/MPR/cleanup_20261105/transport/runtime_views'
capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[
    ('01-main-aerial-preserved',[0,0,0],90000,-52,-90,False),
    ('02-removed-west-spurs',[-100,-380,0],50000,-68,-90,False),
    ('03-two-road-junctions',[-239,-305,0],17000,-68,-90,False),
    ('04-former-sleeper-density-boundary',[460,180,-3],15000,-60,-45,False),
    ('05-railbed-seam-close',[461,180,-3],6500,-28,-135,False),
    ('06-railbed-northeast-low',[625,365,-1],14000,-24,-135,False),
    ('07-interior-preserved',[0,0,4],49000,-60,-90,True),
]
capture.report.update(capture_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    detail_scope='Main warehouse and interior invariant, removed western spurs, two local road junctions, actual 300m sleeper-detail boundary, railbed close and low oblique continuity.',
    target_coordinate_convention='VIEWS target xyz is CAD metres; UE target=(x,-y,z)*100 cm',
    prior_density_boundary_ue_target_m=[460,-180,-3],
    prior_railbed_worst_clearance_ue_m=[627.509,-361.220,-1.395],
    prior_railbed_worst_clearance_to_terrain_m=-.087926)
