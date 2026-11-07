"""Build private open-frame sorter assets without changing existing equipment.

The documented mechanism is a travelling column on a closed chain with a
vertically positioned short-belt tray. CAD64/120 retain their existing plan,
bin locations and modelled four levels; vendor identity/capacity is unconfirmed.
Run in an isolated factory-startup Blender process. All runtime profiles use
Unreal local centimetres; source Blender geometry remains CAD metres (+Y).
"""
import argparse
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import build_mpr_sorter as g

SOURCE=ROOT/'SourceAssets/MPR/equipment'
OUT=ROOT/'SourceAssets/MPR/sorter_simulation'
REMOVED={'MainBelt','BeltSeam','BeltRail','EndMachinery','EndCobaltBand',
         'InspectionWindow','MonitorBody','MonitorGlass','ServiceHandle','BaseShoe'}
NAMES={'SM_MPR_SorterCAD64':('cad64','SM_MPR_SorterSimBody64'),
       'SM_MPR_SorterCAD120':('cad120','SM_MPR_SorterSimBody120')}
TOWER='SM_MPR_SorterSimTower'
TRAY='SM_MPR_SorterSimTray'
PACKAGE='/Game/MPRWarehouse/SorterSimulation/Meshes/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bbox(obj):
    points=[obj.matrix_world@v.co for v in obj.data.vertices]
    return [[min(p[k] for p in points) for k in range(3)],
            [max(p[k] for p in points) for k in range(3)]]


def center(bounds):
    return [(a+b)/2 for a,b in zip(*bounds)]


def ue_cm(point):
    return [point[0]*100,-point[1]*100,point[2]*100]


def add_box(name,point,size,role,col):
    return g.box(name,point,size,role,col)


def track_loop(col,half_straight,radius,z,lod,name):
    """Open-center closed guide, not a solid horizontal obstruction."""
    count=(16,10,6)[lod]
    points=[]
    for cx,start in ((half_straight,-math.pi/2),(-half_straight,math.pi/2)):
        points += [(cx+radius*math.cos(start+math.pi*i/count),
                    radius*math.sin(start+math.pi*i/count),z) for i in range(count+1)]
    for i,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
        g.rod(name+'_'+str(i),a,b,.010,'Metal',col,sides=6)


def profile_from_source(mesh,spec):
    col=bpy.data.collections[mesh+'_Editable_LOD0']
    slots=[];chutes=[o for o in col.objects if o.name.split('.')[0]=='Chute']
    for obj in col.objects:
        name=obj.name.split('.')[0]
        if not re.fullmatch(r'Bin_-?1_\d+_\d+',name):continue
        _,cad_side,column,level=name.split('_');cad_side=int(cad_side);column=int(column)-1;level=int(level)-1
        bounds=bbox(obj);pos=center(bounds)
        expected=.12+level*.445+.23
        chute=min((o for o in chutes if center(bbox(o))[1]*cad_side>0),
                  key=lambda o:abs(center(bbox(o))[0]-pos[0])+abs(center(bbox(o))[2]-expected))
        cb=bbox(chute);entry=[pos[0],cb[0][1] if cad_side>0 else cb[1][1],cb[1][2]]
        outlet=[pos[0],cb[1][1] if cad_side>0 else cb[0][1],cb[0][2]+.015*math.cos(math.radians(20))]
        # Bin inner base is eight millimetres above its external floor.
        drop=[pos[0],pos[1],bounds[0][2]+.008]
        ub=[ue_cm(p) for p in bounds]
        slots.append(dict(side=0 if cad_side<0 else 1,column=column,level=level,
                          chute_entry_cm=ue_cm(entry),chute_outlet_cm=ue_cm(outlet),
                          bin_drop_cm=ue_cm(drop),bin_rim_z_cm=bounds[1][2]*100,
                          bin_bounds_cm=[[min(p[k] for p in ub) for k in range(3)],
                                         [max(p[k] for p in ub) for k in range(3)]],
                          original_bin_object=obj.name,original_chute_object=chute.name))
    slots.sort(key=lambda b:(b['side'],b['column'],b['level']))
    half=(spec['length']-2*spec['end'])/2-.10
    radius=.29 if spec['columns']==8 else .335
    profile_id,body=NAMES[mesh]
    columns=sorted({b['chute_entry_cm'][0] for b in slots})
    levels=[]
    for level in range(4):
        sample=next(b for b in slots if b['level']==level)
        levels.append(dict(level=level,chute_entry_z_cm=sample['chute_entry_cm'][2],
                           tray_carry_z_cm=sample['chute_entry_cm'][2]+1.5,
                           bin_floor_z_cm=sample['bin_drop_cm'][2],bin_rim_z_cm=sample['bin_rim_z_cm']))
    return dict(id=profile_id,static_mesh=PACKAGE+body,tower_mesh=PACKAGE+TOWER,tray_mesh=PACKAGE+TRAY,
                source_mesh=PACKAGE.replace('SorterSimulation','Equipment')+mesh,
                modeled_columns=spec['columns'],modeled_levels=4,sides=2,modeled_capacity=len(slots),
                plan_length_cm=spec['length']*100,plan_width_cm=spec['width']*100,
                track_half_straight_cm=half*100,track_radius_cm=radius*100,
                track_length_cm=(4*half+2*math.pi*radius)*100,
                track_start_cm=[(half+radius)*100,0,0],track_direction='CCW',
                tower_count=4,tower_phase_offsets=[0,.25,.5,.75],tower_height_cm=212,
                tower_column_inward_offset_cm=16,
                tray_size_cm=[32,25],tray_surface_local_z_cm=0,
                parcel_recommended_size_cm=[25,20,14],tray_carry_z_range_cm=[15,190],
                column_x_cm=columns,levels=levels,bins=slots,
                infeed_end_x_cm=(half+radius)*100,infeed_height_cm=103.5,
                infeed_tray_local_cm=[(half+radius)*100,0,103.5],
                capacity_basis='Retained scene model parameters. CAD horizontal columns are evidenced; four vertical levels and vendor identity are not surveyed.',
                path_basis='Presentation motion path fitted inside the retained scene footprint, not surveyed drive-chain dimensions.')


def open_body(mesh,spec,profile,lod):
    source=bpy.data.collections[mesh+'_Editable_LOD'+str(lod)]
    body=NAMES[mesh][1];col=bpy.data.collections.new(body+'_Editable_LOD'+str(lod));bpy.context.scene.collection.children.link(col)
    removed=[];retained=[]
    for obj in source.objects:
        semantic=obj.name.split('.')[0]
        if semantic in REMOVED:
            removed.append(obj.name);continue
        copy=obj.copy();copy.data=obj.data.copy();col.objects.link(copy);copy.hide_set(False);copy.hide_render=False
        retained.append(obj.name)
    h=profile['track_half_straight_cm']/100;r=profile['track_radius_cm']/100
    # Column is 0.16m on the left/inside of the CCW path. The guides follow
    # that actual column location. There is no deck across the lift cavity.
    track_loop(col,h,r-.16,.025,lod,'LowerGuide')
    track_loop(col,h,r-.16,2.14,lod,'UpperGuide')
    # Open rectangular end frames retain the original machine envelope.
    frame_y=spec['width']/2-.505-.04
    for side in (-1,1):
        x=side*(spec['length']/2-.055)
        for y in (-frame_y,frame_y):
            add_box('EndGuidePost',(x,y,1.14),(.035,.035,2.28),'Metal',col)
        add_box('EndGuideCrossbeam',(x,0,2.295),(.045,2*frame_y+.035,.045),'Porcelain',col)
    return col,dict(removed_source_objects=removed,retained_source_objects=retained)


def dynamic_parts():
    """All XY coordinates below are Unreal local; negate Y for source FBX."""
    tower=bpy.data.collections.new(TOWER+'_Editable_LOD0');bpy.context.scene.collection.children.link(tower)
    tray=bpy.data.collections.new(TRAY+'_Editable_LOD0');bpy.context.scene.collection.children.link(tray)
    def box(col,name,p,size,role):return add_box(name,(p[0],-p[1],p[2]),size,role,col)
    # Two runners leave a cavity over the lower guide; both touch floor Z0.
    for x in (-.085,.085):box(tower,'TowerRunner',(x,.11,.02),(.025,.22,.04),'Charcoal')
    box(tower,'TowerBaseBridge',(0,.11,.075),(.195,.22,.03),'Metal')
    box(tower,'TowerColumn',(0,.16,1.09),(.075,.05,2.06),'Metal')
    for x in (-.04,.04):box(tower,'ColumnRail',(x,.128,1.09),(.012,.014,2.02),'Cobalt')
    box(tower,'VerticalTimingBelt',(0,.126,1.09),(.022,.008,1.94),'Rubber')
    for z in (.14,2.04):
        g.rod('TimingPulley',(-.045,-.126,z),(.045,-.126,z),.035,'Cobalt',tower,sides=10)
    box(tower,'TowerTopCap',(0,.16,2.105),(.10,.08,.03),'Porcelain')
    # Centre pivot is the carrying surface. Side rails run in the belt's Y
    # direction and do not obstruct either lateral discharge edge.
    box(tray,'TrayFrame',(0,0,-.035),(.32,.25,.04),'Metal')
    box(tray,'TrayShortBelt',(0,0,-.0075),(.29,.25,.015),'Cobalt')
    for x in (-.154,.154):box(tray,'TraySideRail',(x,0,.015),(.012,.25,.03),'Porcelain')
    for y in (-.09,.09):box(tray,'TrayBeltSeam',(0,y,.001),(.285,.003,.002),'Charcoal')
    # The carriage touches the column guides; it is not a separate free object.
    box(tray,'TrayLiftCarriage',(0,.145,-.035),(.095,.045,.10),'Metal')
    return tower,tray


def build_layout(profiles):
    source=json.loads((SOURCE/'sorter_instances.json').read_text(encoding='utf8'))
    snapshot=ROOT/'SourceAssets/MPR/conveyor_repair_20261106/after_scene.json.gz'
    with gzip.open(snapshot,'rt',encoding='utf8') as stream:scene=json.load(stream)
    available=[]
    for actor in scene['actors']:
        for component in actor.get('components',[]):
            mesh=component.get('mesh','').split('.')[-1]
            if mesh not in NAMES:continue
            for index,transform in enumerate(component.get('instance_transforms',[])):
                available.append((mesh,actor,component,index,transform))
    machines=[]
    for mesh, (profile_id,_) in NAMES.items():
        for row in source['instances'][mesh]:
            point=ue_cm(row['position_m'])
            matches=[a for a in available if a[0]==mesh and math.dist(a[4]['translation_cm'],point)<.01]
            assert len(matches)==1,(row['id'],len(matches))
            _,actor,component,index,transform=matches[0]
            assert transform['scale']==[1.,1.,1.] and all(abs(q)<1e-7 for q in transform['rotation_xyzw'][:3])
            machines.append(dict(id=row['id'],profile=profile_id,actor_guid=actor['guid'],actor_label=actor['label'],
                                 actor_path=actor['path'],component_name=component['name'],instance_index=index,
                                 original_mesh=component['mesh'],world_transform=transform,
                                 cad_source_handle=row['source_handle'],cad_child_handle=row['child_handle'],
                                 infeed_is_presentation_loop_start=True))
    assert len(machines)==22
    return dict(schema_version=1,units='UE cm',axis_contract='Local mesh/profile axes are UE X,Y,Z; apply world_transform once. Source Blender Y was negated exactly once at import.',
                snapshot_map=scene['map'],snapshot_map_file_sha256=scene['map_file_sha256'],
                machines=machines,profiles=profiles,excluded_meshes=['SM_MPR_SorterShort10','SM_MPR_Tiangong96'],
                mechanism='Closed-chain travelling columns; one vertically positioned short-belt tray per column; lateral discharge to fixed chutes and bins.',
                limitations=['This is a scene-model demonstration, not PLC/process telemetry or confirmed production capacity.',
                             'Four trays per machine, speed, flow direction, loading port and timing are presentation choices.',
                             'Original CAD instance positions, bin positions, chutes and modelled levels are retained.'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    assert bpy.data.filepath=='','Run in factory-startup Blender; do not alter a live source scene'
    out=args.output;out.mkdir(parents=True,exist_ok=True);g.OUT=out
    source_blend=SOURCE/'MPR_SorterCADVariants.blend';source_sha=sha(source_blend)
    bpy.ops.wm.open_mainfile(filepath=str(source_blend))
    for obj in bpy.data.objects:obj.hide_set(False)
    g.MATS={role:bpy.data.materials['M_Zcool_'+role] for role in g.ROLES}
    original_objects=set(bpy.data.objects)
    spec_manifest=json.loads((SOURCE/'sorter_variants_manifest.json').read_text(encoding='utf8'))
    specs={s['name']:s for s in spec_manifest['specs']}
    profiles={};rows=[];source_edits={}
    for mesh,(profile_id,name) in NAMES.items():
        profile=profile_from_source(mesh,specs[mesh]);profiles[profile_id]=profile
        for lod in range(3):
            col,edits=open_body(mesh,specs[mesh],profile,lod)
            if lod==0:source_edits[profile_id]=edits
            record=g.export(col,name+('' if lod==0 else '_LOD'+str(lod)));record.update(lod=lod,kind='static_body',profile=profile_id)
            rows.append(record)
            for obj in col.objects:obj.hide_render=lod!=0;obj.hide_set(lod!=0)
    tower,tray=dynamic_parts()
    for col,name in ((tower,TOWER),(tray,TRAY)):
        record=g.export(col,name);record.update(lod=0,kind='dynamic_part',pivot='ground Z0' if name==TOWER else 'carrying surface Z0')
        rows.append(record)
    for obj in list(original_objects):bpy.data.objects.remove(obj,do_unlink=True)
    for col in list(bpy.data.collections):
        if not col.objects and not col.children:bpy.data.collections.remove(col)
    layout=build_layout(profiles)
    for row in rows:
        row['fbx']=str(Path(row['fbx']).relative_to(ROOT)).replace('\\','/')
    for row in rows:
        if row['kind']=='static_body' and row['lod']==0:
            row['lod_files']=[r['fbx'] for r in rows if r.get('profile')==row['profile'] and r['lod']>0]
    manifest=dict(schema_version=1,meshes=rows,profiles=profiles,source_static_body_changes=source_edits,
                  blender=(out/'MPR_SorterSimulation.blend').relative_to(ROOT).as_posix(),
                  preview=(out/'asset_preview.png').relative_to(ROOT).as_posix(),
                  source_files=[dict(path=str(source_blend),sha256=source_sha),
                                dict(path=str(SOURCE/'sorter_instances.json'),sha256=sha(SOURCE/'sorter_instances.json'))],
                  material_paths={r:'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+r for r in g.ROLES},
                  axis_contract='FBX source metres CAD +Y; UE import makes X=100*x,Y=-100*y,Z=100*z. Profiles already use UE local cm.',
                  dynamic_axes='Local +X is CCW path tangent; local +Y is inward left normal. Tray is centred; no outward assumption.',
                  safety='No decorative collision; reuse grouped instancing; simulation actors manage bounded shared updates.')
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'MPR_SorterSimulation.blend'))
    assert sha(source_blend)==source_sha
    print(json.dumps({'meshes':len(rows),'machines':len(layout['machines']),'profiles':list(profiles),'source_unchanged':True}))


if __name__=='__main__':main()
