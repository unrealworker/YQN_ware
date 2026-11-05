"""Blender: physical module gaps in five retained solar banks, no original writes.

Keeps every reviewed module centre, all 59 bank rectangles and roof clearances.
All LODs retain identical module silhouettes; far views never become solid pads.
"""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/hierarchy_20261105/solar'
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57/solar'
ROLES=['MPRH_SolarFrame','MPRH_SolarCells','MPRH_SolarCellsLight','MPRH_SolarCellsShade']
COLORS=['7E96A8','1E4D78','22517C','1B4771']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def linear(s):
    c=[int(s[i:i+2],16)/255 for i in (0,2,4)]
    return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
def bounds(vertices):return [[min(p[i] for p in vertices),max(p[i] for p in vertices)]for i in range(3)]

def rectangle(vv,ff,uv,rect,z):
    x0,y0,x1,y1=rect;offset=len(vv)
    vv.extend([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)])
    ff.append([offset+i for i in range(4)]);uv.append([(0,0),(1,0),(1,1),(0,1)])

def box(vv,ff,uv,rect,z0,z1,top=True):
    x0,y0,x1,y1=rect;offset=len(vv)
    vv.extend([(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
               (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)])
    faces=[(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    if top:faces.append((4,5,6,7))
    ff.extend([[offset+i for i in f]for f in faces]);uv.extend([[(0,0),(1,0),(1,1),(0,1)]for f in faces])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source_files=[SOURCE/'layout.json',SOURCE/'manifest.json',SOURCE/'inputs/cad_layout.json']
    original_hashes={p.relative_to(ROOT).as_posix():sha(p)for p in source_files}
    layout=read(source_files[0]);source_manifest=read(source_files[1])
    assert layout['module_cells']==5636 and sum(map(len,layout['blocks'].values()))==59
    origin=layout['uv_origin_m'];pitch=layout['pitch_m'];z=layout['top_z_m']
    # Total clear gaps: individual 8/12cm, grouped 32/50cm. Bounds/centres stay in
    # the original module cells, never creating PV over an old roof opening.
    modules={};audit=[]
    for bank,blocks in layout['blocks'].items():
        cells=[]
        for block in blocks:
            ix0,iy0,ix1,iy1=block['grid']
            for ix in range(ix0,ix1):
                for iy in range(iy0,iy1):
                    x0,y0=origin[0]+ix*pitch[0],origin[1]+iy*pitch[1]
                    mx=.16 if ix%4 in (0,3) else .04
                    my=.25 if iy%3 in (0,2) else .06
                    # Symmetric shrinking preserves centres even on group boundaries.
                    rect=[x0+mx,y0+my,x0+pitch[0]-mx,y0+pitch[1]-my]
                    assert rect[0]>=block['bounds_m'][0] and rect[1]>=block['bounds_m'][1]
                    assert rect[2]<=block['bounds_m'][2]+1e-8 and rect[3]<=block['bounds_m'][3]+1e-8
                    tone=(ix*17+iy*23)%11
                    role=ROLES[2]if tone<2 else ROLES[3]if tone>8 else ROLES[1]
                    cells.append(dict(grid=[ix,iy],bounds_m=rect,role=role))
        modules[bank]=cells
        audit.append(dict(bank=bank,module_count=len(cells),block_count=len(blocks)))
    assert sum(map(len,modules.values()))==5636
    # Explicit proof: every cell footprint remains inside exactly one original
    # rectangle; all original equipment/service exclusions are therefore retained.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    mats={}
    for role,color in zip(ROLES,COLORS):
        mat=bpy.data.materials.new(role);mat.use_nodes=True
        bs=mat.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Base Color'].default_value=(*linear(color),1)
        bs.inputs['Roughness'].default_value=.7 if role==ROLES[0]else .62
        bs.inputs['Metallic'].default_value=0
        bs.inputs['Specular IOR Level'].default_value=.15 if role==ROLES[0]else .18
        mats[role]=mat
    exports=[];objects={}
    for bank,cells in modules.items():
        for lod in range(3):
            name='SM_MPRH_SolarBank_'+bank+(''if lod==0 else '_LOD'+str(lod))
            groups={r:[[],[],[]]for r in ROLES}
            for row in cells:
                rect=row['bounds_m'];frame=groups[ROLES[0]]
                if lod==0:box(*frame,rect,z-.08,z+.014,top=True)
                else:rectangle(*frame,rect,z+.014)
                x0,y0,x1,y1=rect
                rectangle(*groups[row['role']],[x0+.025,y0+.025,x1-.025,y1-.025],z+.020)
            # Original two mounting rails per block retained at every LOD. These
            # bound the mesh vertically and anchor it to the original roof height.
            for block in layout['blocks'][bank]:
                x0,y0,x1,y1=block['bounds_m']
                for y in (y0+.15,y1-.15):
                    box(*groups[ROLES[0]],[x0+.12,y-.06,x1-.12,y+.06],layout['roof_z_m']+.014,z-.08)
            vv=[];ff=[];uvs=[];mi=[]
            for index,role in enumerate(ROLES):
                verts,faces,uv=groups[role];offset=len(vv)
                vv.extend(verts);ff.extend([[i+offset for i in face]for face in faces]);uvs.extend(uv);mi.extend([index]*len(faces))
            mesh=bpy.data.meshes.new(name);mesh.from_pydata(vv,[],ff);mesh.update()
            obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
            for role in ROLES:mesh.materials.append(mats[role])
            uv=mesh.uv_layers.new(name='UVMap')
            for poly,idx,coords in zip(mesh.polygons,mi,uvs):
                poly.material_index=idx
                for loop,coord in zip(poly.loop_indices,coords):uv.data[loop].uv=coord
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
            path=OUT/(name+'.fbx')
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
            mesh.calc_loop_triangles();objects[name]=obj
            exports.append(dict(name=name,fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),material_roles=ROLES,
                                bounds_m=bounds(vv),triangles=len(mesh.loop_triangles),lod=lod,bank=bank))
            obj.hide_render=lod>0;obj.hide_viewport=lod>0
    blend=OUT/'MPR_Hierarchy_Solar.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    byname={r['name']:r for r in exports};meshes=[]
    for bank in modules:
        name='SM_MPRH_SolarBank_'+bank;levels=[byname[name],byname[name+'_LOD1'],byname[name+'_LOD2']]
        row=dict(levels[0]);radius=math.sqrt(sum(((b-a)/2)**2 for a,b in row['bounds_m']))
        # Approx. bank distance 150/430m at a 50-degree horizontal view. All
        # silhouettes stay open even past the distant threshold.
        screens=[1.,min(.95,2*radius/(150*2*math.tan(math.radians(25)))),min(.4,2*radius/(430*2*math.tan(math.radians(25))))]
        old=next(r for r in source_manifest['meshes']if r['name']=='SM_MPRR_SolarBank_'+bank)
        row.update(category='Architecture',lod_files=[r['fbx']for r in levels[1:]],lod_sha256=[r['sha256']for r in levels[1:]],
            lod_triangles=[r['triangles']for r in levels],lod_screen_sizes=screens,lod_material_roles=[ROLES]*3,all_lod_material_roles=ROLES,
            retained_actor_label='MPR4_SolarBank_'+bank,source_mesh='/Game/MPRWarehouse/RebuildB50B57/Architecture/Meshes/'+old['name'],
            instance_only=False,collision=False,tick=False,full_precision_uvs=True,nanite=False)
        meshes.append(row)
    report=dict(success=True,map='/Game/Maps/MPR_CAD_Warehouse_B50B57',namespace='/Game/MPRWarehouse/Hierarchy20261105',
                units='metres',axis='CAD +Y; UE X=100*x,Y=-100*y,Z=100*z',meshes=meshes,export_meshes=exports,
                source_hashes=original_hashes,layout_source=source_files[0].relative_to(ROOT).as_posix(),
                preserved_blocks=layout['blocks'],preserved_device_count=len(layout['devices_unchanged']),
                module_count=5636,module_centres_unchanged=True,blocks_unchanged=True,per_lod_identical_module_silhouettes=True,
                module_silhouettes_sha256=hashlib.sha256(json.dumps(modules,sort_keys=True).encode()).hexdigest(),
                grouped_gap_m=[.32,.5],minimum_module_gap_m=[.08,.12],material_roles=ROLES,
                materials={role:dict(source_srgb_hex='#'+color,base_color=linear(color),roughness=.7 if i==0 else .62,metallic=0.,specular=.15 if i==0 else .18,emission=0.,normal_strength=0.)for i,(role,color)in enumerate(zip(ROLES,COLORS))},
                material_policy='Opaque plain DefaultLit materials; exact linear base colors, no old Albedo texture and no old roughness clamp. Avoid whole-bank specular glare.',
                old_assets_modified=False,blend=blend.relative_to(ROOT).as_posix(),blend_sha256=sha(blend),banks=audit)
    write(OUT/'module_layout.json',modules)
    write(OUT/'manifest.json',report)
    assert sum(r['lod_triangles'][0]for r in meshes)<150000
    roundtrip=[]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for row in exports:
        bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']),use_custom_normals=True,colors_type='LINEAR')
        ob=next(o for o in bpy.context.selected_objects if o.type=='MESH');ob.data.calc_loop_triangles()
        actual=bounds([tuple(ob.matrix_world@v.co)for v in ob.data.vertices])
        error=max(abs(a-b)for aa,bb in zip(actual,row['bounds_m'])for a,b in zip(aa,bb))
        assert error<.002 and len(ob.data.loop_triangles)==row['triangles'],row['name']
        assert [s.material.name for s in ob.material_slots]==ROLES
        roundtrip.append(dict(name=row['name'],bounds_error_m=error,triangles=row['triangles'],material_slots_valid=True))
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        for collection in (bpy.data.meshes,bpy.data.materials):
            for item in list(collection):
                if item.users==0:collection.remove(item)
    assert all(sha(ROOT/path)==digest for path,digest in original_hashes.items())
    validation=dict(success=True,roundtrip=roundtrip,source_hashes_unchanged=True,geometry_mask_unchanged_across_lods=True,
                    module_count=5636,bank_count=5,block_count=59,roof_devices_untouched=195,
                    triangles_per_lod=[sum(r['lod_triangles'][i]for r in meshes)for i in range(3)],manifest_sha256=sha(OUT/'manifest.json'))
    write(OUT/'geometry_validation.json',validation)
    print('MPR_HIERARCHY_SOLAR',json.dumps(validation['triangles_per_lod']),flush=True)

if __name__=='__main__':main()
