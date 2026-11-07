"""Move the parcel centre from a CAD conveyor edge onto its actual rollers.

Offline preparation keeps the measured CAD edge. UE execution only updates the
existing simulation Actor's embedded layout, with a full scene preservation check.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import apply_mpr_full_sorter_workflow as workflow
import mpr_scene_patch_guard as patch
import rebuild_preservation as guard
SRC=workflow.SRC


def prepare():
    ports=patch.read(SRC/'cad_manual_ports.json');layout=patch.read(SRC/'layout.json')
    records=[]
    for row in ports['rows']:
        edge=row['pickup_line_edge_cad_m'];side=row['infeed_side_local_x']
        row['pickup_ue_cm']=[edge[0]*100+side*22,-edge[1]*100,103.03108891324554]
        row['pickup_surface_calibration']={
            'mesh':'/Game/MPRWarehouse/Operations/Meshes/SM_MPR_Conveyor2m',
            'inward_from_cad_edge_cm':22.,'actual_roller_top_cm':103.03108891324554,
            'package_width_cm':22.,'minimum_roller_edge_clearance_cm':2.18,
            'basis':'Conveyor2m cylinder radius 3.5cm, centre Z100cm, six-sided crown; side beam 7cm, largest width scale1.26. Every 120cm pickup approach checked against existing central conveyor instances.'}
        machine=next(m for m in layout['machines'] if m['id']==row['machine_id'])
        records.append({'id':machine['id'],'before':machine['pickup_ue_cm'],'after':row['pickup_ue_cm']})
        machine['pickup_ue_cm']=row['pickup_ue_cm']
    patch.write(SRC/'cad_manual_ports.json',ports);patch.write(SRC/'layout.json',layout)
    manifest=patch.read(SRC/'manifest.json')
    for row in manifest['source_files']:
        if Path(row['path']).name=='cad_manual_ports.json':row['sha256']=guard.sha(SRC/'cad_manual_ports.json')
    patch.write(SRC/'manifest.json',manifest)
    out=ROOT/'Saved/MPR/full_workflow_20261107/pickup_calibration';out.mkdir(exist_ok=True)
    patch.write(out/'points.json',records)


def apply(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(workflow.MAP)
    before=guard.capture(u,ROOT,workflow.MAP);guard.assert_clean(before)
    last=patch.read(workflow.OUT/'after.json.gz');contract=patch.read(workflow.OUT/'controller.json')
    assert before['map_file_sha256']==last['map_file_sha256']
    workflow.validate_other_actors(last,before,contract['guid'])
    actor=next(a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if a.get_class().get_path_name()==workflow.CLASS)
    old=workflow.props(actor);assert old==contract['properties']
    hashes=guard.content_hashes(ROOT);layout=patch.read(SRC/'layout.json')
    with u.ScopedEditorTransaction('校准MPR输送线接货点与辊筒承载面'):
        actor.modify();actor.set_editor_property('layout_json',json.dumps(layout,ensure_ascii=False,separators=(',',':')))
    actor.set_actor_transform(actor.get_actor_transform(),False,False)
    workflow.validate_preview(u,actor,layout)
    candidate=guard.capture(u,ROOT,workflow.MAP);workflow.validate_other_actors(before,candidate,contract['guid'])
    actual=workflow.props(actor)
    assert {k:v for k,v in old.items() if k!='layout_json'}=={k:v for k,v in actual.items() if k!='layout_json'}
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,workflow.MAP);guard.assert_clean(after)
    workflow.validate_other_actors(before,after,contract['guid'])
    assert all(guard.sha(ROOT/p)==h for p,h in hashes.items() if p!='Content/Maps/MPR_CAD_Warehouse_B50B57.umap')
    patch.write(workflow.OUT/'after.json.gz',after)
    patch.write(workflow.OUT/'controller.json',dict(guid=contract['guid'],properties=actual))
    report=patch.read(workflow.OUT/'apply_report.json');report['map_after']=after['map_file_sha256'];report['pickup_calibration']=True
    report['cart_exit_extension_cm']=100
    patch.write(workflow.OUT/'apply_report.json',report)
    patch.write(workflow.OUT/'pickup_calibration.json',dict(success=True,before=before['map_file_sha256'],after=after['map_file_sha256'],changed_actor_count=1,points=22,other_assets_unchanged=True))


if __name__=='__main__':
    if '--prepare' in sys.argv:prepare()
    else:
        import unreal
        apply(unreal)
