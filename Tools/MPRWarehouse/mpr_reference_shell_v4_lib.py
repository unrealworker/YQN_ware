"""Private mesh/texture/export helpers for MPR reference-shell v4. Metres, CAD +Y."""
import json, math, struct, zlib
from pathlib import Path
from collections import defaultdict
import bpy, bmesh, numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[2]

def solar_lod_screen_sizes(bounds):
    """Equal physical-detail distance across differently sized SolarBanks.

    UE screen size is proportional to the bounds sphere radius. A common
    threshold made the largest bank keep fine gaps a third longer than the
    smallest. Keep the existing 70 m reference budget and scale each bank.
    Camera FOV/LOD factor still controls all banks consistently at runtime.
    """
    radius=math.sqrt(sum(((hi-lo)*.5)**2 for lo,hi in bounds))
    return [1.,.9*radius/70.,.35*radius/70.]

def png(path, pixels):
    a=np.clip(pixels,0,255).astype(np.uint8)
    if a.ndim==2:a=np.repeat(a[:,:,None],3,axis=2)
    h,w,c=a.shape
    def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
    data=b''.join(b'\0'+a[y].tobytes() for y in range(h))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2 if c==3 else 6,0,0,0))+chunk(b'IDAT',zlib.compress(data,9))+chunk(b'IEND',b''))

def make_textures(out):
    """Tileable procedural detail; no reference imagery is baked into materials."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(50472);n=512;y,x=np.mgrid[:n,:n]
    specs={}
    def save(name,a):
        p=out/(name+'.png');png(p,a);return p.relative_to(ROOT).as_posix()
    def normal(h,strength):
        dx=(np.roll(h,-1,1)-np.roll(h,1,1))*strength
        dy=(np.roll(h,-1,0)-np.roll(h,1,0))*strength
        v=np.stack([-dx,-dy,np.ones_like(h)],2);v/=np.linalg.norm(v,axis=2,keepdims=True)
        return (v*.5+.5)*255
    noise=rng.random((n,n))
    grain=(noise-.5)*.075+.02*np.sin(x*.13)*np.sin(y*.17)
    specs['paint']={'albedo':save('T_MPR4_PaintedPanel_Base',245+grain*100),
                    'normal':save('T_MPR4_PaintedPanel_Normal',normal(grain,1.7))}
    weave=.025*np.sin(x*math.pi)+.02*np.cos(y*math.pi/2)
    crease=.06*np.sin(2*math.pi*x/n*3+.3*np.sin(2*math.pi*y/n*2))+.025*np.sin(2*math.pi*y/n*7)
    fabric=grain+weave+crease
    specs['fabric']={'albedo':save('T_MPR4_DockFabric_Base',225+fabric*120),
                     'normal':save('T_MPR4_DockFabric_Normal',normal(fabric,2.5))}
    gx=(x+y)%128;gy=(x-y)%128
    diamond=np.maximum(np.clip(1-np.abs(gx-64)/5,0,1)*np.clip(1-np.abs(gy-64)/42,0,1),
                       np.clip(1-np.abs(gx)/42,0,1)*np.clip(1-np.abs(gy)/5,0,1))
    specs['checker']={'albedo':save('T_MPR4_CheckerPlate_Base',215+diamond*27+grain*80),
                      'normal':save('T_MPR4_CheckerPlate_Normal',normal(diamond*.18,3.0))}
    # One 6 x 12-cell module; UV repeats once per physical solar module.
    h,w=1024,512;yy,xx=np.mgrid[:h,:w];u=xx/w;v=yy/h
    cx=(u*6)%1;cy=(v*12)%1
    base=np.zeros((h,w,3));base[:]=[19,49,83]
    tile=(np.floor(u*6)*7+np.floor(v*12)*11)%13
    base+=((tile-6)*.7)[:,:,None]
    base+=rng.random((h,w,1))*4
    # Detail remains readable nearby without almost-white subpixel glints.
    thin=(np.mod(xx,8)<.7);base[thin]+=2
    bus=(np.abs(cx-.27)<.009)|(np.abs(cx-.73)<.009)
    base[bus]=[34,67,101]
    seam=(cx<.016)|(cy<.011)|(cx>.984)|(cy>.989)
    corner=(np.minimum(cx,1-cx)+np.minimum(cy,1-cy))<.075
    base[seam|corner]=[63,91,119]
    specs['solar']={'albedo':save('T_MPR4_SolarCells_Base',base),
                    'normal':save('T_MPR4_SolarCells_Normal',normal(seam.astype(float)*.018,1.0))}
    # Exactly one physical module per tile: no 6x12 cell/bus pattern at the
    # intermediate distance. A periodic smooth border spans 10% of the tile
    # across its seam (0.112m on X, close to the 0.1072m real strip gap).
    # Blend and apply the native-preview gain in linear light; retain the
    # existing bounded material tint instead of baking an overbright tint.
    def decode_srgb(a):
        a=np.asarray(a,dtype=float)/255
        return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
    def encode_srgb(a):
        a=np.clip(a,0,1)
        return 255*np.where(a<=.0031308,a*12.92,1.055*a**(1/2.4)-.055)
    gain=np.array([1.6/.58,1.58/.83,1.4])
    mu=(xx+.5)/w;mv=(yy+.5)/h
    distance=np.minimum(np.minimum(mu,1-mu),np.minimum(mv,1-mv))
    t=np.clip(distance/.05,0,1);border=1-t*t*(3-2*t)
    body=decode_srgb([21,51,85]);edge=decode_srgb([36,70,105])
    mid=encode_srgb((body+(edge-body)*border[:,:,None])*gain)
    flat=np.zeros((h,w,3));flat[:]=[128,128,255]
    specs['solar_mid']={'albedo':save('T_MPR4_SolarMid_Base',mid),
                        'normal':save('T_MPR4_SolarMid_Normal',flat)}
    # Far surface has no periodic grid. Its low-frequency finish converges to
    # the same blue mean under mip filtering rather than a lattice of glints.
    fy,fx=np.mgrid[:128,:128];far=np.zeros((128,128,3));far[:]=[23,54,87]
    variation=.65*np.cos(2*math.pi*fx/128)+.45*np.cos(2*math.pi*fy/128)
    far=encode_srgb(decode_srgb(far+variation[:,:,None])*gain)
    far_normal=np.zeros_like(far);far_normal[:]=[128,128,255]
    specs['solar_far']={'albedo':save('T_MPR4_SolarFar_Base',far),
                        'normal':save('T_MPR4_SolarFar_Normal',far_normal)}
    return specs

class Geometry:
    def __init__(self, materials):
        self.data=defaultdict(lambda:defaultdict(lambda:[[],[],[]]))
        self.materials=materials

    def mesh(self,name,role,verts,faces,uvs=None):
        v,f,u=self.data[name][role];off=len(v);v.extend(verts)
        f.extend(tuple(off+i for i in face) for face in faces)
        if uvs is not None:u.extend(uvs);return
        scale=self.materials[role].get('uv_tile_m',1.)
        for face in faces:
            p=[Vector(verts[i]) for i in face]
            normal=(p[1]-p[0]).cross(p[2]-p[0]);axis=max(range(3),key=lambda i:abs(normal[i]))
            axes=[i for i in range(3) if i!=axis]
            coords=[(q[axes[0]]/scale,q[axes[1]]/scale) for q in p]
            anchor=np.floor(np.min(coords,axis=0))
            u.append([(a-anchor[0],b-anchor[1]) for a,b in coords])

    def box(self,n,r,c,s,yaw=0,bevel=0):
        if min(s)<=0:return
        if bevel>0:
            bm=bmesh.new();bmesh.ops.create_cube(bm,size=1)
            for v in bm.verts:
                v.co.x*=s[0];v.co.y*=s[1];v.co.z*=s[2]
            bmesh.ops.bevel(bm,geom=list(bm.edges),offset=min(bevel,min(s)*.22),segments=1,affect='EDGES')
            bm.verts.ensure_lookup_table();verts=[tuple(v.co) for v in bm.verts]
            faces=[tuple(v.index for v in f.verts) for f in bm.faces];bm.free()
        else:
            dx,dy,dz=[v/2 for v in s]
            verts=[(-dx,-dy,-dz),(dx,-dy,-dz),(dx,dy,-dz),(-dx,dy,-dz),(-dx,-dy,dz),(dx,-dy,dz),(dx,dy,dz),(-dx,dy,dz)]
            faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        a=math.radians(yaw);co,si=math.cos(a),math.sin(a)
        verts=[(c[0]+co*x-si*y,c[1]+si*x+co*y,c[2]+z) for x,y,z in verts]
        self.mesh(n,r,verts,faces)

    def segment(self,n,r,a,b,w,z,h):
        dx,dy=b[0]-a[0],b[1]-a[1];ll=math.hypot(dx,dy)
        if ll>.002:self.box(n,r,((a[0]+b[0])/2,(a[1]+b[1])/2,z),(ll,w,h),math.degrees(math.atan2(dy,dx)))

    def prism(self,n,r,ps,z0,z1):
        p=[tuple(q[:2]) for q in ps]
        if p[0]==p[-1]:p.pop()
        if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))<0:p.reverse()
        v=[Vector((x,y,z1)) for x,y in p];count=len(v);lookup={tuple(q):i for i,q in enumerate(v)}
        tris=[tuple(i if isinstance(i,int) else lookup[tuple(i)] for i in q) for q in tessellate_polygon([v])]
        self.mesh(n,r,[(x,y,z1) for x,y in p]+[(x,y,z0) for x,y in p],tris+[tuple(i+count for i in reversed(t)) for t in tris]+[(i,i+count,(i+1)%count+count,(i+1)%count) for i in range(count)])

    def cylinder(self,n,r,c,radius,height,segments=12):
        v=[(c[0]+radius*math.cos(i*2*math.pi/segments),c[1]+radius*math.sin(i*2*math.pi/segments),c[2]+z*height/2) for z in (-1,1) for i in range(segments)]
        f=[tuple(reversed(range(segments))),tuple(range(segments,segments*2))]+[(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
        self.mesh(n,r,v,f)

    def solar_surface(self,name,role,polygon,z,uv_period=(1.12,1.95),uv_origin=(0.,0.)):
        """Constrained triangles preserve holes; UVs stay continuous per bank."""
        import shapely
        from shapely.geometry.polygon import orient
        assert polygon.is_valid and not polygon.is_empty
        parts=[polygon] if polygon.geom_type=='Polygon' else list(polygon.geoms)
        for part in parts:
            part=orient(part,sign=1.)
            triangles=shapely.constrained_delaunay_triangles(part)
            assert abs(sum(t.area for t in triangles.geoms)-part.area)<1e-6
            for triangle in triangles.geoms:
                p=list(triangle.exterior.coords)[:-1]
                if sum(a[0]*b[1]-b[0]*a[1]for a,b in zip(p,p[1:]+p[:1]))<0:p.reverse()
                self.mesh(name,role,[(x,y,z)for x,y in p],[(0,1,2)],
                          [[((x-uv_origin[0])/uv_period[0],(y-uv_origin[1])/uv_period[1])for x,y in p]])
            for ring in [part.exterior,*part.interiors]:
                for a,b in zip(ring.coords,list(ring.coords)[1:]):
                    self.mesh(name,'MPR4_SolarFrame',[(a[0],a[1],z-.086),(b[0],b[1],z-.086),
                         (b[0],b[1],z),(a[0],a[1],z)],[(0,1,2,3)])

    def material(self,role,texture_root):
        spec=self.materials[role];m=bpy.data.materials.new(role);m.use_nodes=True
        bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Base Color'].default_value=(*spec['color'],1)
        bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec.get('metallic',0)
        if spec.get('emission'):
            bs.inputs['Emission Color'].default_value=(*spec['color'],1);bs.inputs['Emission Strength'].default_value=spec['emission']
        for kind,path in spec.get('textures',{}).items():
            tex=m.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ROOT/path),check_existing=True)
            tex.image.colorspace_settings.name='Non-Color' if kind=='normal' else 'sRGB'
            if kind=='albedo':
                mix=m.node_tree.nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
                mix.inputs[2].default_value=(*spec['color'],1)
                m.node_tree.links.new(tex.outputs['Color'],mix.inputs[1]);m.node_tree.links.new(mix.outputs[0],bs.inputs['Base Color'])
            elif kind=='normal':
                normal=m.node_tree.nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=spec.get('normal_strength',.3)
                m.node_tree.links.new(tex.outputs['Color'],normal.inputs['Color']);m.node_tree.links.new(normal.outputs['Normal'],bs.inputs['Normal'])
        return m

    def export(self,out,metadata,instances):
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
        masters=bpy.data.collections.new('MODULE_LIBRARY');scene.collection.children.link(masters)
        geometry=bpy.data.collections.new('BUILDING_PARTITIONS');scene.collection.children.link(geometry)
        copies=bpy.data.collections.new('CAD_INSTANCES');scene.collection.children.link(copies)
        mats={r:self.material(r,out) for r in self.materials};objs={};rows=[]
        for name,roles in self.data.items():
            verts=[];faces=[];uvs=[];face_roles=[]
            for role,(vv,ff,uu) in roles.items():
                off=len(verts);verts.extend(vv);faces.extend(tuple(i+off for i in f) for f in ff);uvs.extend(uu);face_roles.extend([role]*len(ff))
            data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
            obj=bpy.data.objects.new(name,data);objs[name]=obj
            instanced=name in instances;(masters if instanced else geometry).objects.link(obj)
            keys=list(roles)
            for role in keys:data.materials.append(mats[role])
            layer=data.uv_layers.new(name='UVMap')
            for face,role,uv in zip(data.polygons,face_roles,uvs):
                face.material_index=keys.index(role)
                for idx,p in zip(face.loop_indices,uv):layer.data[idx].uv=p
            obj['mpr_source_role']='reusable_module' if instanced else 'partition_geometry'
            obj['mpr_units']='metres';obj['mpr_reference_version']=4
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
            path=out/(name+'.fbx')
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
            data.calc_loop_triangles()
            rows.append(dict(name=name,fbx=path.relative_to(ROOT).as_posix(),material_roles=keys,
                bounds_m=[[min(v[i] for v in verts),max(v[i] for v in verts)] for i in range(3)],
                vertices=len(verts),triangles=len(data.loop_triangles),instance_only=instanced,collision=False,tick=False,uv_channels=1))
        for name,obj in objs.items():
            if name.endswith(('_LOD1','_LOD2')):
                obj.hide_render=True;obj.hide_viewport=True
        for name,placements in instances.items():
            assert name in objs,name
            for i,p in enumerate(placements):
                obj=bpy.data.objects.new(f'{name}_I{i:03}',objs[name].data);copies.objects.link(obj)
                obj.location=p['position_m'];obj.rotation_euler.z=math.radians(p.get('rotation_deg',0));obj.scale=p.get('scale',[1,1,1])
        masters.hide_render=True;masters.hide_viewport=True
        manifest=dict(schema_version=4,units='metres',axis='CAD +Y; UE placement X=100*x,Y=-100*y,Z=100*z; negate yaw once',
            meshes=rows,instances=instances,materials=self.materials,**metadata)
        manifest['optimization']={'unique_meshes':len(rows),'unique_triangles':sum(r['triangles'] for r in rows),
            'instance_count':sum(len(p) for p in instances.values()),'material_slots':sum(len(r['material_roles']) for r in rows),
            'draw_strategy':'Static partition meshes; shared modules should be HISM, no per-object Tick or collision. Solar continuous strips with repeating cell texture.'}
        (out/'reference_shell_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,
            default=lambda value:value.item() if isinstance(value,np.generic) else str(value)),encoding='utf8')
        # Preserve editable geometry, texture nodes and linked-module placements.
        for im in bpy.data.images:
            if im.source=='FILE':
                im.pack();im.filepath=bpy.path.relpath(im.filepath,start=str(out))
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'mpr_reference_shell.blend'))
        return manifest
