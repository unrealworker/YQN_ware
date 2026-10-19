"""Finish, measure and save the exterior revision for Blender review only."""
import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Vector

out=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
s=bpy.context.scene
assert s.name=='GHS_MannedForklift_Studio'
asset=bpy.data.collections['MannedForklift_Editable']
root=bpy.data.objects['MF_Root']
if not root.get('V2ContactPolish',False):
    # Seat pose is unchanged; lift boot soles to meet the existing floor mat.
    for o in bpy.data.collections['05_Driver'].objects:
        if o.name.startswith(('DRV_RightBoot','DRV_LeftBoot','DRV_RightLace','DRV_LeftLace')):o.location.z+=.057
        if 'ElbowPatch' in o.name:
            o.data.materials.clear();o.data.materials.append(bpy.data.materials['M_MF_Cloth'])
    for o in bpy.data.collections['04_Cockpit'].objects:
        if o.name.startswith('MF_FootPedal'):o.location.z-=.030
    root['V2ContactPolish']=True

# Weld the lathe axis/seam vertices and consistently orient all edited faces.
for o in asset.all_objects:
    if o.type!='MESH':continue
    if 'MouldedTreadGroove' in o.name:
        # The moulded tread meets a flat ground contact patch on a loaded solid tyre.
        inv=o.matrix_world.inverted()
        for v in o.data.vertices:
            world=o.matrix_world@v.co
            if world.z<0:
                world.z=0;v.co=inv@world
    bm=bmesh.new();bm.from_mesh(o.data)
    if o.name.startswith('MF_V2_'):
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0000001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(o.data);bm.free();o.data.update()

bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get()
verts=[];triangles=0;objects=[];bad=[]
for o in asset.all_objects:
    if o.type not in {'MESH','FONT','CURVE'}:continue
    ev=o.evaluated_get(dg);me=ev.to_mesh()
    points=[o.matrix_world@v.co for v in me.vertices]
    if any(not math.isfinite(c) for p in points for c in p):bad.append(o.name)
    me.calc_loop_triangles();triangles+=len(me.loop_triangles);verts.extend(points);objects.append(o.name)
    ev.to_mesh_clear()
bounds=[[min(p[i] for p in verts),max(p[i] for p in verts)] for i in range(3)]
dimensions=[b-a for a,b in bounds]
assert not bad
assert 3.2<dimensions[0]<3.6 and 1.1<dimensions[1]<1.4 and 2.2<dimensions[2]<2.5
assert abs(bounds[2][0])<.002
assert len(bpy.data.collections['05_Driver'].objects)==97

def bounds_of(obj):
    ev=obj.evaluated_get(dg);me=ev.to_mesh();ps=[obj.matrix_world@v.co for v in me.vertices]
    result=[[min(p[i] for p in ps),max(p[i] for p in ps)] for i in range(3)]
    ev.to_mesh_clear();return result
hat_top=max(bounds_of(o)[2][1] for o in bpy.data.collections['05_Driver'].objects if 'Helmet' in o.name)
roof_bottom=min(bounds_of(o)[2][0] for o in asset.all_objects if o.name.startswith('MF_V2_RoofSlat'))
assert roof_bottom-hat_top>.10
sole_bottom=min(bounds_of(bpy.data.objects[n])[2][0] for n in ['DRV_LeftBootSole','DRV_RightBootSole'])
mat_top=bounds_of(bpy.data.objects['MF_V2_FloorMat'])[2][1]
assert 0<=sole_bottom-mat_top<.003
report={
    'revision':'v2 exterior refinement',
    'source':str(out/'manned_forklift_v2.blend'),
    'reference':r'C:/Users/28109/AppData/Local/Temp/codex-clipboard-6b5572be-cdb4-404c-97b1-8a839760c889.png',
    'units':'metres','dimensions_estimated':True,
    'dimensions_m':dimensions,'bounds_m':bounds,'triangles_evaluated':triangles,
    'editable_parts':len(objects),'driver_parts':97,
    'helmet_roof_clearance_m':roof_bottom-hat_top,'boot_floor_gap_m':sole_bottom-mat_top,
    'front_tyres_ground_z_m':0.0,'front_tyre_fender_radial_gap_m':.344-.315,
    'ue_import_performed':False,
    'notes':['Exterior silhouette prioritized over cabin detailing.','Original version preserved in Saved/Backups/GHS_MannedForklift_20261019/v1_before_exterior_refinement.','Driver pose, hardhat and workwear retained.','No UE asset or map was edited.']}
(out/'manned_forklift_v2_validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
s.eevee.taa_render_samples=96
s.eevee.taa_samples=48
s.render.resolution_x=1440;s.render.resolution_y=1260;s.render.resolution_percentage=100
s.render.filepath=str(out/'manned_forklift_v2_preview.png')
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        sp=area.spaces.active
        sp.region_3d.view_distance=5.1;sp.region_3d.view_location=(.35,0,1.10)
        sp.region_3d.view_rotation=s.camera.rotation_euler.to_quaternion()
        sp.overlay.show_overlays=False
for o in bpy.context.selected_objects:o.select_set(False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'manned_forklift_v2.blend'))
print('V2_SAVED_AND_VALIDATED',json.dumps(report))
bpy.ops.render.render(write_still=True)
print('V2_PREVIEW_RENDERED',s.render.filepath)
