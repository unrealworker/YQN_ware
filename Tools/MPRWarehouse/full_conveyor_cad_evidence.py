"""Read source CAD without importing the side-effecting whole-scene extractor."""
from pathlib import Path
import sys, json, math, hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44
SOURCE=Path('D:/Data/仓库数据/MPR/平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT=ROOT/'SourceAssets/MPR/conveyor_audit_20261107'
class MixedDxfStream:
    def __init__(self,path):self.file=open(path,'rb')
    def readline(self):
        data=self.file.readline().replace(b'\r\n',b'\n')
        try:return data.decode('utf8')
        except UnicodeDecodeError:return data.decode('gb18030',errors='replace')
def points(e):
    t=e.dxftype()
    if t=='LINE':return [e.dxf.start,e.dxf.end]
    if t=='LWPOLYLINE':
        p=list(e.vertices_in_wcs());return p+[p[0]] if e.closed and p else p
    if t=='POLYLINE':return list(e.points())
    if t in ('ARC','CIRCLE'):
        a=0 if t=='CIRCLE' else e.dxf.start_angle;b=360 if t=='CIRCLE' else e.dxf.end_angle
        if b<=a:b+=360
        return [(e.dxf.center.x+e.dxf.radius*math.cos(math.radians(a+(b-a)*i/32)),e.dxf.center.y+e.dxf.radius*math.sin(math.radians(a+(b-a)*i/32)),e.dxf.center.z) for i in range(33)]
    return []
def extract(doc,es,mt,chain):
    rows=[]
    for e in es:
        ch=chain+[e.dxf.handle]
        if e.dxftype()=='INSERT':rows.extend(extract(doc,doc.blocks.get(e.dxf.name),Matrix44.chain(e.matrix44(),mt),ch))
        else:
            ps=list(mt.transform_vertices(points(e)))
            if len(ps)>1:rows.append({'type':e.dxftype(),'source_handles':ch,'points_cad_m':[[round((p[0]-12800)*.0254,8),round((p[1]-8000)*.0254,8)] for p in ps]})
    return rows
def main():
    doc=ezdxf.read(MixedDxfStream(SOURCE))
    layout=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
    byhandle={h:v for v in layout['equipment'] for h in v['source_handles']}
    ramps=[]
    for h in ('2CCF62','2CCF66','2E7F10'):
        e=doc.entitydb[h];ramps.append({'source_handle':h,'placement':byhandle[h],'primitives':extract(doc,doc.blocks.get(e.dxf.name),e.matrix44(),[h])})
    marks=[v for v in layout['equipment'] if v['block']=='A$Cb1177cf1']
    assert len(marks)==108
    e=doc.entitydb['2D437C'];symbol=extract(doc,doc.blocks.get(e.dxf.name),e.matrix44(),['2D437C'])
    assert len(symbol)==3 and sorted(x['type'] for x in symbol)==['LINE','LINE','LWPOLYLINE']
    result={'schema_version':1,'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'ramps':ramps,'floor_placeholder_placements':marks,'floor_placeholder_symbol':symbol,'limits':'Plan geometry only. Supply ramp elevation, belt travel direction and material handoff are display assumptions; no bridging equipment is inferred.'}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'cad_source_evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('FULL_CONVEYOR_CAD_EVIDENCE',len(ramps),len(marks))
if __name__=='__main__':main()
