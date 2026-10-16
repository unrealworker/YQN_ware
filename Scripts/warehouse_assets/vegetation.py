"""Deterministic branching broadleaf trees, in metres, for the logistics park."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *
import random


class TreeMesh:
    def __init__(self, rng):
        self.rng = rng
        self.vertices, self.faces, self.material_ids = [], [], []
        self.leaf_count = 0

    def face(self, indices, material_id):
        self.faces.append(tuple(indices))
        self.material_ids.append(material_id)

    def branch(self, points, radii, sides=7):
        """Tapered, gently irregular tubes with aligned ring seams."""
        offset = len(self.vertices)
        for i, (p, radius) in enumerate(zip(points, radii)):
            tangent = (points[min(i + 1, len(points)-1)] - points[max(i-1, 0)]).normalized()
            side = tangent.cross(Vector((0, 1, 0))).normalized()
            if side.length < 0.1:
                side = tangent.cross(Vector((1, 0, 0))).normalized()
            up = tangent.cross(side).normalized()
            for j in range(sides):
                angle = j * math.tau / sides
                irregularity = 1 + 0.045 * math.sin(j * 2.7 + i * 0.65)
                self.vertices.append(p + radius * irregularity * (math.cos(angle)*side + math.sin(angle)*up))
        self.face([offset+j for j in reversed(range(sides))], 0)
        for i in range(len(points)-1):
            for j in range(sides):
                a = offset + i*sides + j
                b = offset + i*sides + (j+1)%sides
                self.face((a, b, b+sides, a+sides), 0)
        self.face([offset+(len(points)-1)*sides+j for j in range(sides)], 0)

    def leaf(self, center, length, width, normal, twist):
        """A pointed seven-vertex leaf, with lifted midrib and a drooping tip."""
        normal = normal.normalized()
        along = normal.cross(Vector((math.cos(twist), math.sin(twist), 0.15))).normalized()
        across = normal.cross(along).normalized()
        o = len(self.vertices)
        coords = [(0, -0.50, 0), (0, 0, .10), (0, .50, -.10),
                  (-.43, -.13, 0), (-.31, .22, -.015),
                  (.43, -.13, 0), (.31, .22, -.015)]
        for x, y, z in coords:
            self.vertices.append(center + x*width*across + y*length*along + z*length*normal)
        boundary = [0,3,4,2,6,5]
        # Sunlit leaves form fewer lighter patches than midtone and shaded leaves.
        mat = self.rng.choices((1,2,3), (0.46,0.37,0.17))[0]
        for a, b in zip(boundary, boundary[1:]+boundary[:1]):
            self.face((o+1, o+a, o+b), mat)
        self.leaf_count += 1


def vdirection(angle, elevation):
    return Vector((math.cos(angle)*math.cos(elevation), math.sin(angle)*math.cos(elevation), math.sin(elevation)))


def create_tree(name, height, width, seed, columnar=False):
    rng = random.Random(seed)
    g = TreeMesh(rng)
    h = height
    # Buttressed roots and an asymmetrically leaning, high-clearance street trunk.
    trunk = [Vector((0,0,0)),Vector((.04,-.015,.3*h)),Vector((-.08,.04,.46*h)),
             Vector((.05,.07,.64*h)),Vector((.13,.02,.82*h)),Vector((.09,.05,.96*h))]
    trunk_r = [.215,.17,.135,.095,.05,.008] if not columnar else [.18,.14,.115,.08,.045,.008]
    g.branch(trunk, trunk_r, 12)
    for root in range(7):
        a = math.tau*root/7 + rng.uniform(-.15,.15)
        g.branch([Vector((0,0,.27)),vdirection(a,.05)*.25+Vector((0,0,.07)),vdirection(a,0)*rng.uniform(.5,.78)], [.16,.105,.007], 8)

    # Primary limbs make distinct layered, irregular lobes, with visible crotches.
    primary_count = 12 if columnar else 10
    target_leaves = 10600 if name.endswith('_A') else (8500 if name.endswith('_B') else 9400)
    cluster_sites = []
    for p in range(primary_count):
        angle = p * 2.399963 + rng.uniform(-.26,.26)
        z = h*(.31 + .043*p) if not columnar else h*(.27 + .048*p)
        start = Vector((.025*math.sin(z), .03*math.cos(z), z))
        radial = width * (.37 if not columnar else .26) * (1 - .032*p)
        radial *= rng.uniform(.85,1.10)
        rise = h*rng.uniform(.12,.22) if not columnar else h*rng.uniform(.20,.31)
        end = start + Vector((math.cos(angle)*radial,math.sin(angle)*radial,rise))
        mid = start.lerp(end,.43) + Vector((-.07,.04,-.10))
        g.branch([start,mid,end], [rng.uniform(.065,.092),.045,.013], 8)
        # Secondary limbs fork outward; their tips carry narrow leafy shoots.
        for q in range(5):
            origin = mid.lerp(end, .14+q*.17)
            a = angle + (-1 if q%2 else 1)*rng.uniform(.27,.85)
            reach = width*rng.uniform(.115,.205) if not columnar else width*rng.uniform(.12,.21)
            tip = origin + vdirection(a,rng.uniform(.25,.85))*reach + Vector((0,0,rng.uniform(.1,.4)))
            bend = origin.lerp(tip,.55) + Vector((0,0,-.07))
            g.branch([origin,bend,tip],[.026,.014,.0035],6)
            for t in range(3):
                attach = bend.lerp(tip,t/3)
                theta = a+rng.uniform(-1.25,1.25)
                shoot = attach+vdirection(theta,rng.uniform(.1,1.15))*rng.uniform(.31,.61)
                g.branch([attach,attach.lerp(shoot,.6),shoot],[.0075,.004,.0011],5)
                cluster_sites.append((shoot, rng.uniform(.27,.48),rng.uniform(.22,.39)))
    # An upright leader closes the upper canopy without a flat top.
    for j in range(14):
        angle = j*2.399963
        start = trunk[3].lerp(trunk[5],j/16)
        tip = start + vdirection(angle,rng.uniform(.35,1.0))*rng.uniform(.32,.68)
        g.branch([start,start.lerp(tip,.5),tip],[.016,.008,.0015],6)
        cluster_sites.append((tip,.30,.30))
    for index, (site, rx, rz) in enumerate(cluster_sites):
        count = target_leaves//len(cluster_sites)+(index<target_leaves%len(cluster_sites))
        for leaf_index in range(count):
            # Clustered twigs have gaps; each cluster contains real leaf blades.
            az = rng.uniform(0,math.tau)
            cz = rng.uniform(-1,1)
            r = rng.random()**.45
            xy = math.sqrt(1-cz*cz)
            position = site+Vector((rx*r*xy*math.cos(az),rx*r*xy*math.sin(az),rz*r*cz))
            normal = Vector((rng.uniform(-.7,.7),rng.uniform(-.7,.7),rng.uniform(.12,1)))
            length = rng.uniform(.18,.29) if not columnar else rng.uniform(.15,.25)
            g.leaf(position,length,length*rng.uniform(.48,.69),normal,rng.uniform(0,math.tau))
    # Exact family envelope keeps placement, variety selection and bounds predictable.
    low = [min(v[i] for v in g.vertices) for i in range(3)]
    high = [max(v[i] for v in g.vertices) for i in range(3)]
    sx, sy = width/(high[0]-low[0]), width*.91/(high[1]-low[1])
    sz = height/(high[2]-low[2])
    for v in g.vertices:
        v.x *= sx
        v.y *= sy
        v.z = (v.z-low[2])*sz
    obj = mesh(name,g.vertices,g.faces,bark)
    for mat in greens:
        obj.data.materials.append(mat)
    for poly, mat_id in zip(obj.data.polygons,g.material_ids):
        poly.material_index = mat_id
        poly.use_smooth = mat_id == 0
    result = export_asset(name,[obj])
    result.update(leaves=g.leaf_count, origin='trunk ground', foliage_geometry='individual curved seven-vertex leaf blades',
                  collision_recommendation='trunk only; foliage no collision')
    return result


reset()
bark = material('Tree_Bark',(.18,.125,.075),.96,texture_role='bark')
greens = [material('Tree_Leaf_Mid',(.105,.225,.035),.85,two_sided=True,foliage=True),
          material('Tree_Leaf_Shade',(.055,.135,.020),.85,two_sided=True,foliage=True),
          material('Tree_Leaf_Light',(.20,.34,.065),.85,two_sided=True,foliage=True)]
for mat in greens:
    mat.use_backface_culling = False
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    if 'Subsurface Weight' in bsdf.inputs:
        bsdf.inputs['Subsurface Weight'].default_value = .06
assets = [create_tree('SM_Tree_Plane_A',9,6,574),
          create_tree('SM_Tree_Plane_B',7,5,872),
          create_tree('SM_Tree_Columnar',8,3,441,True)]
save_manifest('vegetation.json',assets)
print('TREE_STATS '+json.dumps(assets))

# Re-import delivered files so the preview verifies the actual exported assets.
for i, asset in enumerate(assets):
    bpy.ops.import_scene.fbx(filepath=asset['fbx'])
    obj = bpy.context.selected_objects[0]
    obj.location.x = (i-1)*7
    # FBX importer retains Blender node materials from their source names.
    for index, mat in enumerate(obj.data.materials):
        clean_name = mat.name.split('.')[0]
        original = bpy.data.materials.get(clean_name)
        if original:
            obj.data.materials[index] = original
floor_mat=material('Preview_Ground',(.22,.24,.20),.95)
box('Preview Ground',(0,0,-.12),(27,16,.20),floor_mat,0)
world = bpy.context.scene.world
world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.63,.73,.85,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.45
bpy.ops.object.light_add(type='AREA', location=(-6,-8,15))
bpy.context.object.data.energy=2100
bpy.context.object.data.shape='DISK'
bpy.context.object.data.size=9
bpy.ops.object.light_add(type='SUN', location=(0,0,12))
bpy.context.object.rotation_euler=(.5,-.35,-.5)
bpy.context.object.data.energy=2.1
bpy.ops.object.camera_add(location=(15,-27,13))
cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,4))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO'
cam.data.ortho_scale=26
scene=bpy.context.scene
scene.camera=cam
scene.render.engine='CYCLES'
scene.cycles.samples=24
scene.render.resolution_x=1500
scene.render.resolution_y=850
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(OUT/'vegetation_preview.png')
scene.view_settings.view_transform='AgX'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'vegetation_preview.blend'))
bpy.ops.render.render(write_still=True)
