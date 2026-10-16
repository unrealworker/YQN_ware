"""Replace plan dock-door symbols previously mistaken for storage racks."""
import json,sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/video_reference'))
import common as c
c.reset();c.OUT=ROOT/'SourceAssets/GHS/RackSpecs/Doors';c.OUT.mkdir(parents=True,exist_ok=True)
panel=c.material('M_CADDock_Panel',(.09,.18,.29),.6,.15)
frame=c.material('M_CADDock_Frame',(.04,.1,.18),.55,.3)
dark=c.material('M_CADDock_Dark',(.008,.016,.03),.8,.0)
detail=c.material('M_CADDock_Detail',(.08,.3,.43),.6,.1)
c.begin_asset('SM_GHS_CADDockDoor')
width=119.75*.0254;leaf=110*.0254;depth=.1876647153;height=4.2
guide=(width-leaf)/2
for side in [-1,1]:
    c.box('Door guide rail',(side*(width/2-guide/2),0,height/2),(guide,depth,height),frame,.004)
c.box('Head casing',(0,0,height-.085),(width,depth,.17),frame,.006)
c.box('Shadow gasket',(0,-.045,(height-.17)/2),(leaf,.04,height-.17),dark,.001)
bottom=.04;top=height-.17;count=24;pitch=(top-bottom)/count
for i in range(count):
    c.box('Roller shutter slat %02d'%i,(0,0,bottom+(i+.5)*pitch),(leaf,.045,pitch-.006),panel,.002)
c.box('Bottom seal',(0,.015,.025),(leaf,.065,.05),dark,.002)
for side in [-1,1]:
    c.box('Guide detail',(side*(leaf/2+.006),depth/2-.012,height/2),(.008,.015,height-.17),detail,.001)
c.save_library('cad_dock_door')
p=c.OUT/'cad_dock_door.json';d=json.loads(p.read_text())
d.update(classification='loading_dock_door',not_storage_rack=True,
    measured_plan_width_m=width,measured_leaf_width_m=leaf,
    display_height_m=height,height_basis='4.2 m industrial-door display estimate; plan has no elevation dimension')
p.write_text(json.dumps(d,indent=2),encoding='utf-8')
