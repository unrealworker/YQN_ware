"""Native close views for coupled vehicles, pond paving and campus planting."""
from pathlib import Path
import hashlib,json,math,sys
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_reference_runtime_views as capture

source=capture.ROOT/'SourceAssets/MPR/reference_v4/site/manifest.json'
site=json.loads(source.read_text(encoding='utf8'))
capture.OUT=capture.ROOT/'Saved/MPR/feedback_v7/detail_views'
capture.OUT.mkdir(parents=True,exist_ok=True)
truck=next(r for r in site['instances']['SM_MPR4_Tractor'] if r.get('assembly_id')=='DockSouth_5')
loco=next(r for r in site['instances']['SM_MPR4_Locomotive'] if r.get('consist_id')=='MainEastInner')
car=next(r for r in site['instances']['SM_MPR4_FreightBoxcar'] if r.get('consist_id')=='MainFreight' and r.get('consist_index')==9)
tx,ty,tz=truck['position_m'];lx,ly,lz=loco['position_m'];cx,cy,cz=car['position_m']
angle=math.radians(car['rotation_deg'])
joint=[cx+10.38*math.cos(angle),cy+10.38*math.sin(angle),cz+.86]
capture.VIEWS=[
 ('19-truck-whole',[tx,ty+4.84,1.0],2800,-14,-135,False),
 ('20-truck-cab-wheel',[tx,ty-1.36,-.2],950,-7,-125,False),
 ('21-locomotive-whole',[lx,ly,1.5],2800,-13,-16,False),
 ('22-rail-coupling-wheel',joint,1250,-6,53.69,False),
 ('23-train-consist',[cx,cy,1.2],12000,-24,0,False),
 ('24-pond-paving',[-207,-151,-1.1],11000,-58,-35,False),
 ('25-campus-planting',[0,-30,0],43000,-57,-90,False),
]
capture.report['detail_source_manifest_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
capture.report['capture_tool_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
capture.report['detail_scope']='Native wheel-ground contact, tractor cabin, continuous train, closed pond paving and separate campus planting.'
