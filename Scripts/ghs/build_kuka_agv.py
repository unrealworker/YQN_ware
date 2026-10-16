"""Offline editable low-profile KUKA reference approximation, metres, front +Y."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'video_reference'))
import common as c
import bpy
from mathutils import Vector
c.OUT=Path(__file__).resolve().parents[2]/'SourceAssets'/'GHS'
c.OUT.mkdir(parents=True,exist_ok=True)
c.reset(); c.begin_asset('SM_GHS_KukaLowProfileAGV')
def mat(n,col,r=.5,m=0,**kw): return c.material('M_VR_GHS_AGV_'+n,col,r,m,**kw)
white=mat('WarmWhite',(.79,.82,.82),.3,.12)
gray=mat('SideGray',(.24,.29,.31),.36,.35)
dark=mat('Chassis',(.035,.043,.047),.48,.25)
rubber=mat('Rubber',(.006,.008,.009),.95)
next(n for n in rubber.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Specular IOR Level'].default_value=0.04
orange=mat('KukaOrange',(.95,.19,.018),.33)
metal=mat('Fasteners',(.34,.38,.4),.25,.8)
black=mat('OpticalGlass',(.006,.018,.023),.15,.45)
green=mat('GreenLED',(.012,.9,.12),.25,emission=4)
red=mat('EmergencyRed',(.7,.015,.012),.28)
yellow=mat('SafetyYellow',(.95,.65,.015),.38)
def box(n,loc,sz,ma,edge=.006): return c.box(n,loc,sz,ma,edge)
def rr(n,z,w,l,h,rad,ma): return c.rounded_box(n,(0,0,z),(w,l,h),rad,ma)
# layered molded shell and exposed dark perimeter beneath it
rr('Rubber_perimeter_bumper',.054,.9,1.4,.048,.095,rubber)
rr('Structural_base',.09,.877,1.376,.064,.09,dark)
rr('Lower_white_shell',.155,.89,1.388,.144,.102,white)
rr('Continuous_shadow_seam',.226,.875,1.37,.011,.09,dark)
rr('Upper_white_crown',.269,.9,1.4,.079,.11,white)
rr('Deck_recess',.305,.76,1.21,.018,.055,gray)
box('Rubber_load_surface',(0,0,.317),(.686,1.12,.006),rubber,.001)
# chamfered rim rails flank load platform, create stepped profile
for s in [-1,1]:
 box('Side_gray_fascia', (s*.452,0,.266),(.014,1.065,.074),gray,.007)
 box('Lower_side_access_panel',(s*.446,-.025,.157),(.008,.97,.108),white,.004)
 box('Panel_joint_front',(s*.451,.421,.154),(.002,.003,.105),gray,.0003)
 box('Panel_joint_rear',(s*.451,-.48,.154),(.002,.003,.105),gray,.0003)
 box('Lower_side_reinforcement',(s*.442,-.055,.079),(.016,.83,.018),dark,.004)
 # arrows in plane X constant, point toward +Y
 for y in [-.425,-.38,-.335,.33,.375,.42]:
  x=s*.460; z=.271
  v=[(x,y-.012,z+.022),(x,y+.012,z+.022),(x,y+.035,z),(x,y+.012,z-.022),(x,y-.012,z-.022),(x,y+.01,z)]
  c.mesh('Orange_direction_chevron',v,[(0,1,2,3,4,5)],orange)
 for y in [-.43,.39]:
  for z in [.119,.192]:
   c.cylinder('Recessed_torx_screw',(s*.452,y,z),.0034,.002,metal,16,'X')
 # emergency mushrooms, yellow surround with dark collar
 c.cylinder('Estop_yellow_surround',(s*.454,.507,.159),.024,.008,yellow,48,'X')
 c.cylinder('Estop_black_collar',(s*.461,.507,.159),.016,.008,dark,32,'X')
 c.cylinder('Estop_red_button',(s*.47,.507,.159),.015,.014,red,48,'X')
 # text flat to side, local text X mapped to world longitudinal direction
 rot=(math.pi/2,0,math.pi/2 if s==1 else -math.pi/2)
 c.text('KUKA_side_wordmark','KUKA',(s*.454,.24 if s==1 else -.24,.135),.034,orange,rot)
 c.text('Serial_number','00002',(s*.454,-.16 if s==1 else .16,.137),.025,gray,rot)
 box('Black_brand_plaque',(s*.454,-.32,.179),(.004,.11,.05),black,.002)
 c.text('Plaque_KUKA','KUKA',(s*.458,-.32,.171),.014,orange,rot)
# front and rear sensor / LED arrays
for s in [-1,1]:
 box('End_inset_gray',(0,s*.688,.23),(.57,.012,.037),gray,.006)
 box('End_green_status_band',(0,s*.698,.231),(.49,.003,.008),green,.001)
 box('End_camera_housing',(0,s*.7,.276),(.058,.008,.018),dark,.003)
 for x in [-.014,.014]: c.cylinder('End_camera_lens',(x,s*.706,.276),.004,.003,black,24,'Y')
 for x in [-.349,.349]:
  box('Corner_laser_dark_recess',(x,s*.637,.222),(.106,.081,.033),dark,.012)
  box('Corner_laser_optical_window',(x,s*.703,.224),(.071,.009,.018),black,.004)
  box('Corner_ready_LED',(x,s*.684,.267),(.022,.004,.009),green,.001)
# Separate positive-height steps avoid coplanar raster/depth artifacts in UE:
# rubber top .320; ring spans .3205-.322; lift disc spans .3225-.324.
c.cylinder('Central_turntable_ring',(0,0,.32125),.128,.0015,dark,96)
c.cylinder('Central_lift_disc',(0,0,.32325),.088,.0015,metal,96)
assert .32125-.0015/2 > .317+.006/2
assert .32325-.0015/2 > .32125+.0015/2
for x in [-.285,.285]:
 for y in [-.48,.48]:
  box('Deck_panel_outline',(x,y,.3216),(.056,.083,.0016),gray,.001)
  for dy in [-.031,.031]: c.cylinder('Deck_screw',(x,y+dy,.3229),.002,.0006,metal,16)
# wheels are mostly concealed inside the skirt
for x in [-.34,.34]:
 for y in [-.43,.43]: c.cylinder('Concealed_wheel',(x,y,.042),.042,.05,rubber,40,'X')
# editable components are saved; exported copies are joined and triangulatable in UE
c.save_library('kuka_agv')
# offline studio preview, excluded from asset collection and export
scene=bpy.context.scene
scene.render.engine='CYCLES'; scene.cycles.samples=48
scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.world.color=(.23,.23,.23)
def aim(o,p): o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(1.65,2.12,1.2));cam=bpy.context.object;aim(cam,(0,0,.14));scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=1.93
for loc,power,size in [((1.2,1.2,2.7),280,2.5),((-1.6,.4,1.8),210,2),((0,-2,2),260,2)]:
 bpy.ops.object.light_add(type='AREA',location=loc);lamp=bpy.context.object;lamp.data.energy=power;lamp.data.shape='DISK';lamp.data.size=size;aim(lamp,(0,0,.1))
scene.view_settings.view_transform='AgX'
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(c.OUT/'KukaAGV_Preview.png')
bpy.ops.render.render(write_still=True)
print('GHS_AGV_PREVIEW_COMPLETE')



