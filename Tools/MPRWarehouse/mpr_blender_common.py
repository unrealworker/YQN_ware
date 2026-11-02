"""Small deterministic mesh builder. Metres, CAD +Y, FBX mirrors Y in UE."""
import json
import math
from pathlib import Path
from collections import defaultdict
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[2]
PALETTE = json.loads((ROOT/'SourceAssets/GHS/Park/reference_style.json').read_text(encoding='utf-8'))['palette']
PALETTE.update(Porcelain=[.83,.85,.88], Cobalt=[.018,.075,.51], Metal=[.43,.49,.57],
               Charcoal=[.055,.075,.11], Glass=[.055,.14,.22], Solar=[.045,.075,.13],
               Floor=[.63,.68,.73], Rubber=[.025,.035,.055], SoftBlue=[.24,.39,.68])

class Geometry:
    def __init__(self):
        self.data = defaultdict(lambda: defaultdict(lambda: [[], []]))

    def mesh(self, name, role, vertices, faces):
        vv, ff = self.data[name][role]
        offset=len(vv); vv.extend(vertices); ff.extend(tuple(i+offset for i in f) for f in faces)

    def box(self,name,role,center,size,yaw=0):
        x,y,z=center; dx,dy,dz=[v/2 for v in size]; c=math.cos(math.radians(yaw));s=math.sin(math.radians(yaw))
        verts=[(x+c*a-s*b,y+s*a+c*b,z+h) for a,b,h in
               [(-dx,-dy,-dz),(dx,-dy,-dz),(dx,dy,-dz),(-dx,dy,-dz),
                (-dx,-dy,dz),(dx,-dy,dz),(dx,dy,dz),(-dx,dy,dz)]]
        self.mesh(name,role,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def segment(self,name,role,a,b,width,z,height):
        dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
        if length<.002:return
        self.box(name,role,((a[0]+b[0])/2,(a[1]+b[1])/2,z),(length,width,height),math.degrees(math.atan2(dy,dx)))

    def prism(self,name,role,points,z0,z1):
        pts=[tuple(p[:2]) for p in points]
        if pts[0]==pts[-1]:pts.pop()
        if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts,pts[1:]+pts[:1]))<0:pts.reverse()
        loop=[Vector((x,y,z1)) for x,y in pts]; n=len(pts)
        triangles=tessellate_polygon([loop]); lookup={tuple(v):i for i,v in enumerate(loop)}
        top=[tuple(v if isinstance(v,int) else lookup[tuple(v)] for v in t) for t in triangles]
        self.mesh(name,role,[(x,y,z1) for x,y in pts]+[(x,y,z0) for x,y in pts],
                  top+[tuple(i+n for i in reversed(t)) for t in top]+[(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)])

    def export(self,out,stem,metadata=None):
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
        result=[]
        for name, roles in self.data.items():
            verts=[];faces=[];face_roles=[]
            for role,(vv,ff) in roles.items():
                off=len(verts);verts.extend(vv);faces.extend(tuple(i+off for i in f) for f in ff);face_roles.extend([role]*len(ff))
            data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
            obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
            for role in roles:
                mat=bpy.data.materials.get(role) or bpy.data.materials.new(role);mat.use_nodes=True
                bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
                bs.inputs['Base Color'].default_value=(*PALETTE.get(role,[.5,.6,.7]),1)
                bs.inputs['Roughness'].default_value=.76;obj.data.materials.append(mat)
            keys=list(roles)
            for f,role in zip(data.polygons,face_roles):f.material_index=keys.index(role)
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
            fbx=out/(name+'.fbx')
            bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
            data.calc_loop_triangles()
            result.append(dict(name=name,fbx=fbx.relative_to(ROOT).as_posix(),material_roles=keys,
                               bounds_m=[[min(v[i] for v in verts),max(v[i] for v in verts)] for i in range(3)],
                               vertices=len(verts),triangles=len(data.loop_triangles)))
        bpy.ops.wm.save_as_mainfile(filepath=str(out/(stem+'.blend')))
        manifest=dict(schema_version=1,units='metres',axis='CAD +Y; UE import X=100*x,Y=-100*y,Z=100*z',meshes=result,**(metadata or {}))
        (out/(stem+'.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print('MPR_GEOMETRY',stem,len(result),sum(r['triangles'] for r in result))
        return manifest
