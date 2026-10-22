"""Verify and photograph saved double-pallet floor loads in an owned game."""
import hashlib
import json
from pathlib import Path
import time
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/DoublePallet'
assert '-RenderOffscreen' in unreal.SystemLibrary.get_command_line()
world=pc=hud=pawn=None
result=dict(success=False,views=[],groups=[])
map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash=hashlib.sha256(map_file.read_bytes()).hexdigest()

def wait(check,seconds=45):
    until=time.monotonic()+seconds
    while not check():
        assert time.monotonic()<until,'Runtime condition timed out'
        yield

def pause(seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:yield

def discover():
    global world,pc,hud,pawn
    for w in unreal.ObjectIterator(unreal.World):
        c=unreal.GameplayStatics.get_player_controller(w,0)
        h=getattr(c,'twin_hud_widget',None) if c else None
        if h and h.browser_ready:
            world,pc,hud,pawn=w,c,h,c.get_controlled_pawn()
            return True
    return False

def capture(name):
    dest=OUT/(name+'.png');old=dest.stat().st_mtime_ns if dest.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot filename="'+dest.as_posix()+'" -nosuffix',pc)
    yield from wait(lambda:dest.exists() and dest.stat().st_mtime_ns!=old)
    result['views'].append(str(dest))

def run():
    yield from wait(discover)
    assert pc.warehouse_roof.is_roof_closed()
    yield from wait(lambda:not pawn.is_pose_transition_active())
    hud.open_warehouse()
    yield from wait(pc.warehouse_roof.is_interior_available)
    hud.set_visibility(unreal.SlateVisibility.HIDDEN)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    by={a.get_actor_label():a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)}
    baseline=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
    for label,suffix,count in [('GHS_CAD_PalletCargoHigh','High',1900),('GHS_CAD_PalletCargo','Mid',3726),('GHS_CAD_PalletCargoLow','Low',1904)]:
        actor=by[label];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert component.get_instance_count()==count
        assert component.static_mesh.get_path_name().startswith('/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/')
        assert [component.get_material(i).get_path_name() for i in range(component.get_num_materials())]==baseline['actors'][label]['components'][0]['materials']
        transform=component.get_instance_transform(0,world_space=True)
        center=unreal.MathLibrary.transform_location(transform,component.static_mesh.get_bounds().origin)
        pawn.focus_on_target(center,850.,unreal.Rotator(pitch=-24,yaw=-110,roll=0),
            unreal.Vector2D(1600,1000),unreal.Vector2D(800,500),.4)
        yield from wait(lambda:not pawn.is_pose_transition_active())
        yield from pause(1.5)
        yield from capture('DoublePallet_'+suffix)
        if suffix=='High':
            component.set_forced_lod_model(4)
            yield from pause(.6)
            yield from capture('DoublePallet_High_LOD3')
            component.set_forced_lod_model(0)
        result['groups'].append(dict(actor=label,count=count,mesh=component.static_mesh.get_path_name()))
    assert hashlib.sha256(map_file.read_bytes()).hexdigest()==map_hash
    result.update(success=True,instances=sum(r['count'] for r in result['groups']),saved_map_unchanged=True)

sequence=run()
def tick(delta):
    try:
        next(sequence);return
    except StopIteration:pass
    except Exception:result['error']=traceback.format_exc()
    (OUT/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.SystemLibrary.execute_console_command(world,'quit',pc)
handle=unreal.register_slate_post_tick_callback(tick)
