"""Restore full floor storage and place static 1..87 exterior shutter numbers.

The numbering is spatial, east wall north-to-south then south wall east-to-west.
CAD door identifiers are retained solely to match existing geometry, never as
the displayed number. Run in the live editor via the local GHS dispatcher.
"""
import hashlib
import importlib
import json
import math
import shutil
import sys
import traceback
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT/'Saved/DockNumbers'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
PREFIX = 'GHS_DockNumber_'
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def xyz(v): return [float(v.x),float(v.y),float(v.z)]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def geometry_signature(by):
    result={}
    for label, actor in by.items():
        if label.startswith(PREFIX) or label.startswith('GHS_CAD_PalletCargo'): continue
        c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        if not c: continue
        transforms=[]
        for i in range(c.get_instance_count()):
            t=c.get_instance_transform(i,world_space=True)
            transforms.append([round(v,7) for v in xyz(t.translation)+xyz(t.scale3d)+[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w]])
        result[label]=dict(mesh=c.static_mesh.get_path_name(),count=c.get_instance_count(),
            transforms=hashlib.sha256(json.dumps(transforms).encode()).hexdigest())
    return result

def make_rows():
    envelope=read(ROOT/'SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json')
    mesh=envelope['meshes']['SM_GHS_V2ExteriorFaces']
    segments=[]
    for face in mesh['faces']:
        points=[mesh['vertices'][i] for i in face]
        if min(p[2] for p in points)<4.19: continue
        a,b=points[:2]
        segments.append(([a[0]*100,-a[1]*100],[b[0]*100,-b[1]*100]))
    doors=read(ROOT/'SourceAssets/GHS/RefinementV2/Envelope/door_docking_targets.json')['doors']
    doors=sorted(doors,key=lambda d:(0,-d['door_center_cad_m'][1]) if d['outward_unit_normal_ue'][0]>.5 else (1,-d['door_center_cad_m'][0]))
    assert len(doors)==87 and len({d['instance_id'] for d in doors})==87
    rows=[]
    for number,door in enumerate(doors,1):
        x,y,z=door['door_center_cad_m']; center=[x*100,-y*100,z*100]
        normal=door['outward_unit_normal_ue']; tangent=[-normal[1],normal[0]]
        intersections=[]
        for a,b in segments:
            qa=sum((a[i]-center[i])*tangent[i] for i in range(2))
            qb=sum((b[i]-center[i])*tangent[i] for i in range(2))
            if abs(qb-qa)<1e-7: continue
            u=-qa/(qb-qa)
            if not -1e-8<=u<=1+1e-8: continue
            d=sum((a[i]+u*(b[i]-a[i])-center[i])*normal[i] for i in range(2))
            if abs(d)<80: intersections.append(d)
        assert intersections,(number,'No exterior wall at lintel')
        offset=max(intersections)+1.5
        rows.append(dict(number=number,instance_id=door['instance_id'],door_center=center,
            normal=normal,wall_surface_offset=max(intersections),
            location=[center[0]+normal[0]*offset,center[1]+normal[1]*offset,center[2]+500.],
            yaw=math.degrees(math.atan2(normal[1],normal[0]))))
    return rows

def verify(rows, baseline):
    by={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
    assert geometry_signature(by)==baseline,'Existing non-floor geometry changed'
    labels=[a for label,a in by.items() if label.startswith(PREFIX)]
    assert len(labels)==87
    for row in rows:
        actor=by[PREFIX+str(row['number'])]
        c=actor.get_component_by_class(unreal.TextRenderComponent)
        assert str(c.text)==str(row['number'])
        assert (actor.get_actor_location()-unreal.Vector(*row['location'])).length()<.02
        assert (actor.get_actor_forward_vector()-unreal.Vector(*row['normal'])).length()<1e-5
        color=c.text_render_color
        assert [color.r,color.g,color.b,color.a]==[5,19,130,255]
        assert c.get_editor_property('mobility')==unreal.ComponentMobility.STATIC
        assert not actor.get_actor_enable_collision()
    floor={}
    for label,count in [('GHS_CAD_PalletCargo',3726),('GHS_CAD_PalletCargoLow',1904),('GHS_CAD_PalletCargoHigh',1900)]:
        c=by[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert c.get_instance_count()==count
        assert not c.static_mesh.get_name().endswith('_Occ70')
        floor[label]=count
    return dict(labels=87,number_range=[1,87],floor_instances=sum(floor.values()),floor_groups=floor,
        existing_non_floor_geometry_preserved=True,static_labels=True)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(success=False)
    try:
        assert EDITOR.get_editor_world().get_path_name().split('.')[0]==MAP
        assert not LEVELS.is_in_play_in_editor()
        dirty=unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        assert not dirty or ((OUT/'map_before.umap').exists() and all(p.get_path_name()==MAP for p in dirty))
        original=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse.umap'
        original_hash=sha(original)
        if not (OUT/'map_before.umap').exists(): shutil.copy2(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',OUT/'map_before.umap')
        by={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
        baseline=geometry_signature(by)
        rows=make_rows()
        doors=by['GHS_CAD_DockDoors'].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        positions=[doors.get_instance_transform(i,world_space=True).translation for i in range(doors.get_instance_count())]
        assert len(positions)==87
        for row in rows:
            indices=[i for i,p in enumerate(positions) if (p-unreal.Vector(*row['door_center'])).length()<.1]
            assert len(indices)==1,(row['number'],indices)
            row['door_instance_index']=indices[0]
        sys.path.insert(0,str(ROOT/'Scripts/ghs'))
        import restore_zcool_floor
        importlib.reload(restore_zcool_floor)
        report['floor']=restore_zcool_floor.restore_floor(by)
        text_material=by['GHS_SiteTitle'].get_component_by_class(unreal.TextRenderComponent).text_material
        for row in rows:
            label=PREFIX+str(row['number'])
            actor=by.get(label)
            if actor is None:
                actor=ACTORS.spawn_actor_from_class(unreal.TextRenderActor,unreal.Vector(*row['location']),unreal.Rotator(yaw=row['yaw']))
                actor.set_actor_label(label)
            actor.set_actor_location(unreal.Vector(*row['location']),False,True)
            actor.set_actor_rotation(unreal.Rotator(yaw=row['yaw']),True)
            actor.set_actor_enable_collision(False)
            actor.set_actor_tick_enabled(False)
            actor.set_folder_path('GHS/Annotations/DockNumbers')
            actor.tags=['GHSDigitalTwin','ZcoolSequentialDockNumber','DoorInstance='+row['instance_id'],'DisplayNumber='+str(row['number'])]
            c=actor.get_component_by_class(unreal.TextRenderComponent)
            c.set_text(str(row['number']))
            c.set_world_size(60.)
            c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
            c.set_vertical_alignment(unreal.VerticalTextAligment.EVRTA_TEXT_CENTER)
            c.set_text_render_color(unreal.Color(r=5,g=19,b=130,a=255))
            c.set_text_material(text_material)
            c.set_mobility(unreal.ComponentMobility.STATIC)
        report['before_reload']=verify(rows,baseline)
        assert LEVELS.save_current_level()
        assert sha(original)==original_hash,'Original NormalWarehouse map changed'
        # Verify reload in a fresh process. The live bridge retains Python object
        # references, so in-place LoadLevel would prevent old-world GC.
        report.update(success=True,saved=True,saved_and_reloaded=False,original_map_preserved=True,
            numbering='East wall north to south, then south wall east to west',rows=rows)
        write(ROOT/'SourceAssets/GHS/ZcoolDockNumbers.json',dict(numbering=report['numbering'],rows=rows))
    except Exception:
        report['error']=traceback.format_exc()
        unreal.log_error(report['error'])
    write(OUT/'apply_report.json',report)
    assert report['success'],report.get('error')

if __name__=='__main__': main()
