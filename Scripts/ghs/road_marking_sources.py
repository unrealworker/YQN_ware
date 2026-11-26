"""Collect the survey-aligned lane ribbons used by the park and road continuation builders."""
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import build_park_geometry as park
import build_context_transition as context
import park_site

OUT=ROOT/'Saved/GHSRenderQuality/RoadAssets'


def collect():
    origins=park.ORIGIN
    faces=[]
    def emit(role,vertices,quads):
        if role!='Markings':
            return
        # ribbon() emits alternating left and right corners for every centerline point.
        points=[]
        for i,(x,y,z) in enumerate(vertices):
            px,py,_=vertices[i^1]
            points.append([(x-origins[0])*100,(y-origins[1])*100,z*100,(x-px)*50,(y-py)*50])
        faces.extend([[points[j] for j in quad] for quad in quads])
    original=park.mesh
    park.mesh=emit
    class EndRoads(Exception): pass
    def end_roads(*args,**kwargs): raise EndRoads()
    # build_site emits all road ribbons before installing the fence/parking/vehicles.
    api={'mesh':lambda *args:None,'poly':lambda *args:None,'box':lambda *args:None,'ribbon':park.ribbon,
         'counts':defaultdict(int),'preview':[],'warehouse':park.WAREHOUSE,'context_roads':[]}
    fence=park_site.build_fence
    park_site.build_fence=end_roads
    try:
        try: park_site.build_site(api)
        except EndRoads: pass
        assert faces
        main=list(faces)
        faces.clear()
        roads=json.loads((ROOT/'SourceAssets/GHS/Traffic/routes.json').read_bytes())['roads']
        cad=json.loads((ROOT/'SourceAssets/GHS/Park/cad_layout.json').read_bytes())['roads']
        context.road_ends(roads,cad)
        assert faces
        terminal=list(faces)
    finally:
        park_site.build_fence=fence
        park.mesh=original
    OUT.mkdir(parents=True,exist_ok=True)
    for label,rows in [('park',main),('terminal',terminal)]:
        (OUT/(label+'-source-quads.json')).write_text(json.dumps(rows,separators=(',',':')),encoding='utf8')
        print(label,len(rows),flush=True)

if __name__=='__main__':
    collect()
