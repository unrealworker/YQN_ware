"""Build the independently hideable, CAD-fitted GHS warehouse roof.

Run in background Blender. Only MainRoof source files and ParkRoofStyle logs
are written; the original warehouse, park, UE assets and shared materials are
read-only. The editable .blend keeps all roof elements separate; FBX contains
one closed multi-material static mesh with a stable five-slot contract.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GHS/MainRoof'
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
sys.dont_write_bytecode=True

import bpy
import bmesh
from mathutils import Vector
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

NAME='SM_GHS_MainWarehouseRoof'
ORIGIN=(239.33385,60.24019)
RIDGE=59.436
DEPTH=118.872
BOTTOM=9.60
EAVE=9.76
RIDGE_TOP=10.40
ROLES=('Roof','Seams','Blue','Skylight','Detail')
PALETTE={
    'Roof':((.78,.83,.90),.75,.08),
    'Seams':((.63,.71,.81),.8,.05),
    'Blue':((.035,.13,.48),.8,.05),
    'Skylight':((.24,.45,.70),.42,.05),
    'Detail':((.60,.67,.74),.8,.05),
}
SOURCE=ROOT/'SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def parts(shape):
    if shape.is_empty:return []
    if shape.geom_type=='Polygon':return [shape]
    return [p for item in getattr(shape,'geoms',[]) for p in parts(item)]


def elevation(u,v):
    if v<=0 or v>=DEPTH:return EAVE
    return EAVE+(RIDGE_TOP-EAVE)*(1-abs(v-RIDGE)/RIDGE)


def geometry(shape,bottom,top):
    """Closed solids, split at every roof slope change, sharing exact vertices."""
    vertices=[];faces=[];index={}
    def point(u,v,z):
        key=(round(u,8),round(v,8),round(z,8))
        if key not in index:
            index[key]=len(vertices)
            vertices.append((u-ORIGIN[0],-(v-ORIGIN[1]),z))
        return index[key]
    def add(coords):
        # Reflection of v into Blender Y reverses all face windings.
        faces.append(list(reversed([point(*p) for p in coords])))
    cuts=(-1000.,0.,RIDGE,DEPTH,1000.)
    for poly in parts(shape):
        poly=orient(poly,sign=1)
        for lo,hi in zip(cuts,cuts[1:]):
            sliced=poly.intersection(box(-1000,lo,1500,hi))
            for piece in parts(sliced):
                for tri in constrained_delaunay_triangles(piece).geoms:
                    if tri.area<1e-10:continue
                    assert tri.difference(piece).area<1e-7
                    coords=list(orient(tri,sign=1).exterior.coords)[:3]
                    add([(u,v,top(u,v)) for u,v in coords])
                    add([(u,v,bottom(u,v)) for u,v in reversed(coords)])
        for ring in (poly.exterior,*poly.interiors):
            for a,b in zip(ring.coords,list(ring.coords)[1:]):
                ts=[0.,1.]
                if abs(b[1]-a[1])>1e-9:
                    ts += [(c-a[1])/(b[1]-a[1]) for c in cuts[1:-1]
                           if 1e-9<(c-a[1])/(b[1]-a[1])<1-1e-9]
                points=[(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t) for t in sorted(ts)]
                for (u0,v0),(u1,v1) in zip(points,points[1:]):
                    add([(u0,v0,bottom(u0,v0)),(u1,v1,bottom(u1,v1)),
                         (u1,v1,top(u1,v1)),(u0,v0,top(u0,v0))])
    return vertices,faces


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Save checksums of source inputs and every existing shared UE/material
    # asset before creating anything. The generator never opens or writes them.
    protected=[SOURCE,ROOT/'SourceAssets/GHS/wall_height_profile.json',
               ROOT/'SourceAssets/GHS/Park/scene_overrides.json',
               *sorted((ROOT/'Content/GHSZcoolSmartFactory/Materials').glob('*.uasset')),
               *sorted((ROOT/'Content/GHSZcoolSmartFactory/Park/Materials').glob('*.uasset'))]
    hashes={str(p):sha(p) for p in protected}
    source=json.loads(SOURCE.read_text(encoding='utf-8'))
    outline=[(x/100+ORIGIN[0],y/100+ORIGIN[1]) for x,y in source['main_building_polygon_ue_cm']]
    footprint=Polygon(outline)
    roof=footprint.buffer(.25,join_style='mitre')
    assert roof.is_valid and roof.covers(footprint)
    assert abs(footprint.area-56116.09826824961)<.00001
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.name='GHS_MainWarehouseRoof_Source'
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    scene.render.engine='CYCLES';scene.cycles.samples=16
    materials={}
    for role,(color,roughness,metallic) in PALETTE.items():
        material=bpy.data.materials.new('M_GHSMainRoof_'+role)
        material.diffuse_color=(*color,1);material.use_nodes=True
        principled=next((n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if principled is None:
            principled=material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            output=material.node_tree.nodes.new('ShaderNodeOutputMaterial')
            material.node_tree.links.new(principled.outputs['BSDF'],output.inputs['Surface'])
        principled.inputs['Base Color'].default_value=(*color,1)
        principled.inputs['Roughness'].default_value=roughness
        principled.inputs['Metallic'].default_value=metallic
        materials[role]=material
    collection=bpy.data.collections.new('Editable_MainRoof_Parts')
    scene.collection.children.link(collection)
    records=[];objects=[]
    def solid(name,shape,role,bottom,top):
        if shape.is_empty:return
        vertices,faces=geometry(shape,bottom,top)
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata(vertices,[],faces);mesh.update()
        assert not mesh.validate(verbose=True),name
        mesh.materials.append(materials[role])
        bm=bmesh.new();bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        assert all(e.is_manifold for e in bm.edges),(name,'non-manifold edge')
        assert all(f.calc_area()>1e-10 for f in bm.faces),(name,'degenerate face')
        assert bm.calc_volume(signed=True)>0,(name,'inside-out solid')
        bm.to_mesh(mesh);bm.free();mesh.calc_loop_triangles()
        obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj)
        obj['roof_part']=name;obj['material_role']=role
        objects.append(obj)
        records.append(dict(name=name,role=role,vertices=len(mesh.vertices),triangles=len(mesh.loop_triangles),closed=True))
        return obj
    roof_body=solid('RoofBody_ClosedCADEnvelope',roof,'Roof',lambda u,v:BOTTOM,elevation)
    sky_centers=(75.,155.,235.,315.,395.)
    sky_shapes=[box(u-1.8,15,u+1.8,105) for u in sky_centers]
    skylights=unary_union(sky_shapes)
    for i,(u,shape) in enumerate(zip(sky_centers,sky_shapes),1):
        assert roof.covers(shape)
        # Opaque blue inserts sit just above the white roof. Avoid transparent
        # sorting and retain an entirely watertight hideable roof assembly.
        solid('Skylight_%02d_BlueBand'%i,shape,'Skylight',lambda u,v:elevation(u,v)+.004,lambda u,v:elevation(u,v)+.045)
        frame=shape.buffer(.07,join_style='mitre').difference(shape.buffer(-.035,join_style='mitre'))
        solid('Skylight_%02d_PerimeterFrame'%i,frame,'Seams',lambda u,v:elevation(u,v)+.045,lambda u,v:elevation(u,v)+.095)
        for n in range(1,15):
            v=15+n*6
            solid('Skylight_%02d_Mullion_%02d'%(i,n),box(u-1.8,v-.035,u+1.8,v+.035),'Seams',lambda u,v:elevation(u,v)+.045,lambda u,v:elevation(u,v)+.09)
    seam_count=0
    for n in range(1,311):
        u=n*1.5
        strip=box(u-.035,-1,u+.035,139).intersection(roof.buffer(-.42,join_style='mitre')).difference(skylights.buffer(.1,join_style='mitre'))
        if strip.is_empty:continue
        solid('StandingSeam_%03d'%n,strip,'Seams',lambda u,v:elevation(u,v)+.005,lambda u,v:elevation(u,v)+.035)
        seam_count+=1
    rim=roof.difference(roof.buffer(-.36,join_style='mitre'))
    solid('BluePerimeterCap',rim,'Blue',lambda u,v:elevation(u,v)+.008,lambda u,v:elevation(u,v)+.07)
    # White sides are part of the closed body and terminate exactly at 9.60 m.
    # An explicit ridge cap reads in close-up without adding a central ridge wall.
    ridge_shape=box(-1,RIDGE-.13,467,RIDGE+.13).intersection(roof.buffer(-.36,join_style='mitre'))
    solid('RidgeCap',ridge_shape,'Roof',lambda u,v:elevation(u,v)+.006,lambda u,v:elevation(u,v)+.06)
    vents=[]
    for row,v in enumerate((11.,109.)):
        for n,u in enumerate((35.,90.,145.,200.,255.,310.,365.,420.,450.)):
            plinth=box(u-1.0,v-.8,u+1.0,v+.8)
            assert roof.covers(plinth) and not plinth.intersects(skylights)
            z=elevation(u,v)
            solid('Vent_%02d_%02d_Curb'%(row,n),plinth,'Detail',lambda u,v:elevation(u,v)+.006,lambda u,v,z=z:z+.36)
            solid('Vent_%02d_%02d_Cap'%(row,n),box(u-1.15,v-.95,u+1.15,v+.95),'Roof',lambda u,v,z=z:z+.36,lambda u,v,z=z:z+.55)
            vents.append(dict(center_uv_m=[u,v],height_above_roof_m=.55))
    for i,u in enumerate((12.,33.)):
        solid('OfficeVent_%02d'%i,box(u-.8,128-.65,u+.8,128+.65),'Detail',lambda u,v:EAVE+.01,lambda u,v:EAVE+.32)
    # Export geometry uses stable role slots irrespective of editable part order.
    vertices=[];faces=[];slots=[]
    for obj in objects:
        start=len(vertices);vertices.extend([tuple(v.co) for v in obj.data.vertices])
        faces.extend([[start+i for i in poly.vertices] for poly in obj.data.polygons])
        slots.extend([ROLES.index(obj['material_role'])]*len(obj.data.polygons))
    merged=bpy.data.meshes.new(NAME)
    merged.from_pydata(vertices,[],faces);merged.update()
    assert not merged.validate(verbose=True)
    for role in ROLES:merged.materials.append(materials[role])
    for poly,slot in zip(merged.polygons,slots):poly.material_index=slot
    merged.calc_loop_triangles()
    assert len(merged.loop_triangles)<60000
    export=bpy.data.objects.new(NAME,merged);scene.collection.objects.link(export)
    bpy.ops.object.select_all(action='DESELECT');export.select_set(True);bpy.context.view_layer.objects.active=export
    fbx=OUT/(NAME+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
        mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
    bounds=[[min(v.co[i] for v in merged.vertices),max(v.co[i] for v in merged.vertices)] for i in range(3)]
    ue_bounds=dict(min=[bounds[0][0]*100,-bounds[1][1]*100,bounds[2][0]*100],
                   max=[bounds[0][1]*100,-bounds[1][0]*100,bounds[2][1]*100])
    assert abs(ue_bounds['min'][2]-960.)<.001
    row=dict(name=NAME,role='Roof',fbx=str(fbx.relative_to(ROOT)),vertices=len(merged.vertices),
        triangles=len(merged.loop_triangles),source_parts=len(records),bounds_ue_cm=ue_bounds,
        blender_bounds_m=bounds,material_roles=list(ROLES),slot_names=[materials[r].name for r in ROLES],sha256=sha(fbx))
    # Hide the export-only duplicate in the editable source, keeping named parts.
    export.hide_render=True;export.hide_set(True);export.select_set(False)
    scene.world.color=(.55,.58,.63)
    camera_data=bpy.data.cameras.new('Roof_QA_Camera')
    camera=bpy.data.objects.new('Roof_QA_Camera',camera_data);scene.collection.objects.link(camera)
    target=Vector((-6.46,-9.5,9.8));camera.location=target+Vector((40,-440,420))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.type='ORTHO';camera_data.ortho_scale=530;scene.camera=camera
    for name,loc,energy,size in [('Key',(-100,-120,240),400000,200),('Fill',(160,100,180),200000,180)]:
        data=bpy.data.lights.new(name,'AREA');ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob)
        ob.location=loc;ob.rotation_euler=(target-ob.location).to_track_quat('-Z','Y').to_euler()
        data.energy=energy;data.shape='DISK';data.size=size
    scene.render.resolution_x=1800;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.render.film_transparent=False;scene.view_settings.view_transform='AgX'
    scene.render.filepath=str(OUT/'roof_preview.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MainWarehouseRoof.blend'))
    bpy.ops.render.render(write_still=True)
    assert all(sha(Path(p))==h for p,h in hashes.items()),'Shared source or material changed'
    manifest=dict(version=1,name='GHS independent main warehouse roof',
        purpose='White model campus exterior; one independent removable roof, interaction-ready grouping only',
        coordinate_contract='u,v metres; Blender (u-239.33385,-(v-60.24019),z); FBX -Y forward Z up; UE origin, scale1 in cm',
        source_footprint_uv_m=outline,roof_outline_uv_m=list(roof.exterior.coords),
        overhang_m=.25,bottom_elevation_m=BOTTOM,eave_surface_m=EAVE,ridge_v_m=RIDGE,ridge_surface_m=RIDGE_TOP,
        existing_rack_top_m=9.154,minimum_rack_clearance_m=BOTTOM-9.154,
        source_height_status='9.6m existing display walls; roof pitch/details from user visual reference, not measured elevations',
        asset_count=1,mesh=row,meshes=[row],triangles_total=row['triangles'],
        materials={r:dict(color_linear=list(PALETTE[r][0]),roughness=PALETTE[r][1],metallic=PALETTE[r][2]) for r in ROLES},
        material_properties={r:dict(color=list(PALETTE[r][0]),roughness=PALETTE[r][1],metallic=PALETTE[r][2],opaque=True) for r in ROLES},
        skylight_bands=[dict(center_u_m=u,v_range_m=[15,105],width_m=3.6,cells=15) for u in sky_centers],
        standing_seams=dict(count=seam_count,pitch_m=1.5,height_m=.03,width_m=.07),
        main_vent_count=len(vents),office_vent_count=2,vents=vents,parts=records,
        recommended_actor=dict(label='GHS_MainWarehouseRoof',tags=['GHS_WarehouseRoof','RemovableRoof'],
            transform=dict(position_cm=[0,0,0],rotation_deg=[0,0,0],scale=[1,1,1]),collision=False,tick=False,independent_visibility=True),
        checks=dict(source_footprint_fully_covered=roof.covers(footprint),uncovered_area_m2=footprint.difference(roof).area,
            exterior_cad_area_m2=footprint.area,roof_plan_area_m2=roof.area,all_parts_closed=True,all_faces_valid=True,
            material_slot_order=list(ROLES),skylight_count=5,all_skylights_inside=True,vent_skylight_overlap=False,
            shared_sources_unchanged=True,shared_assets_sha256=hashes,triangle_budget=60000),
        outputs=dict(blend='SourceAssets/GHS/MainRoof/MainWarehouseRoof.blend',fbx=row['fbx'],preview='SourceAssets/GHS/MainRoof/roof_preview.png'))
    write('roof_manifest.json',manifest)
    print('GHS_MAIN_ROOF_READY '+json.dumps(dict(triangles=row['triangles'],parts=len(records),skylights=5,main_vents=len(vents),bounds_ue_cm=ue_bounds)))


if __name__=='__main__':main()
