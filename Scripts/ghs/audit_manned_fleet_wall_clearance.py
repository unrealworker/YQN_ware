import sys,json
from pathlib import Path
sys.path.insert(0,'D:/UEPro/Test/Scripts/ghs')
import import_manned_forklift_fleet as f
by=f.util.labels();plan=f.util.read(f.PLAN_PATH);walls=[]
for name in sorted(f.util.WALLS):
    for tri in f.util.world_triangles(by[name]):
        walls.append((name,tri,[min(p[i] for p in tri) for i in range(3)]+[max(p[i] for p in tri) for i in range(3)]))
out=[]
for row in plan['placements']:
    box=row['clear_passage']['bounds_cm']
    out.append(dict(label=row['label'],box=box,conflicts=[dict(wall=n,triangle=t,bounds=b) for n,t,b in walls if f.util.overlap_z(box,b) and f.util.xy_gap(box,b)<=0]))
mesh=f.LIB.load_asset(f.MESH_PATH)
f.util.write(f.ROOT/'Saved/GHS_MannedFleetWallAudit.json',dict(rows=out,lod_triangles=[mesh.get_num_triangles(i) for i in range(4)]))
