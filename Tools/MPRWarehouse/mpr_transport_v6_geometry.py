"""Grounded MPR transport modules; preserves the reviewed tree and GHS library.

Tractor origin is its fifth wheel. Trailer +X faces away from the dock.
Rail stock origin is the rail contact plane; coupler faces are +/-10.38m.
"""
from pathlib import Path
import hashlib, math
import bpy
from mpr_reference_props_geometry import Mesh, wheel, freight


def tractor():
    m=Mesh()
    source=Path(__file__).resolve().parents[2]/'SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    prefixes=('Sculpted cab','Windscreen','Side glazing','Cab door','Cab blue','Cab step',
              'Mirror','Headlamp','Windshield','Front grille','Grille slat','Front bumper','Front license','Cab roof')
    with bpy.data.libraries.load(str(source),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n.startswith(prefixes)]
    objects=[o for o in dst.objects if o is not None]
    assert len(objects)>20,'Missing editable GHS cabin source'
    role_map={'Body':'VehicleWhite','Trim':'VehicleMetal','Accent':'TrailerBlue',
              'Glass':'VehicleGlass','Rubber':'VehicleRubber','Headlight':'ReflectWhite','TailLight':'ReflectRed'}
    for ob in objects:bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    for ob in objects:
        ev=ob.evaluated_get(deps);me=ev.to_mesh()
        points=[]
        for v in me.vertices:
            p=ob.matrix_world@v.co
            # GHS cab begins at 12.23m; fifth wheel anchor shifts it to 2.18m.
            points.append((p.x-10.05,p.y,p.z+.07))
        for face in me.polygons:
            role=role_map[me.materials[face.material_index].name.rsplit('_',1)[-1]]
            m.emit(role,[points[i] for i in face.vertices],[tuple(range(len(face.vertices)))],face.use_smooth)
        ev.to_mesh_clear()
    for ob in objects:bpy.data.objects.remove(ob,do_unlink=True)
    # No enlarged full-detail tire treads/lugs: shared 12-segment opaque wheels.
    for y in (-.70,.70):m.box('VehicleDark',(.95,y,.84),(6.0,.16,.22))
    m.box('VehicleMetal',(0,0,1.16),(1.0,.88,.12),.04)
    for x in (-.88,.48):
        m.branch('VehicleDark',(x,-1.12,.51),(x,1.12,.51),.09,.09,8)
        for y in (-1.16,-.91,.91,1.16):wheel(m,x,y,.51,.51,.22,1)
    for y in (-1.04,1.04):wheel(m,3.43,y,.51,.51,.26,1)
    for y in (-1.02,1.02):
        m.box('VehicleMetal',(1.48,y,.83),(.85,.40,.55),.06)
        m.box('VehicleMetal',(1.95,y,.61),(.42,.38,.10))
        m.box('VehicleRubber',(-1.50,y,.48),(.06,.52,.62))
    return m,dict(kind='tractor_unit',front_axis='+X',origin='fifth-wheel ground projection',
                  axle_centers_x_m=[-.88,.48,3.43],wheel_radius_m=.51,wheel_contact_z_m=0.,
                  coupler_height_m=1.22,cab_source=str(source),cab_source_sha256=digest,
                  cab_reused_part_count=len(objects),ground_origin=True,estimated_dimensions=True)


def connected_boxcar():
    m,meta=freight(1)
    # Source wheel treads were too widely spaced: retain geometry but map their
    # wheel groups from +/-0.85m to the actual +/-0.7625m rail-head centre lines.
    for i,p in enumerate(m.vertices):
        x,y,z=p
        if z<.98 and abs(y)>.60 and any(abs(x-b)<1.55 for b in (-6.3,6.3)):
            m.vertices[i]=(x,y-math.copysign(.0875,y),z)
    meta.update(ground_origin=True,rail_contact_z_m=0.,coupler_x_m=[-10.38,10.38],
                bogie_centers_x_m=[-6.3,6.3],wheel_radius_m=.48,wheel_axis_gauge_m=1.525,
                collision_body_bounds_m=[[-9.4,9.4],[-1.64,1.64],[1.22,4.43]],continuous_consist=True)
    return m,meta


def locomotive():
    m=Mesh()
    m.box('VehicleDark',(0,0,1.03),(19.1,2.55,.44))
    m.box('FreightRoof',(0,0,1.35),(19.0,3.05,.22))
    m.box('VehicleGray',(-1.40,0,2.66),(13.6,2.05,2.42),.08)
    m.box('VehicleGray',(6.10,0,2.90),(3.25,2.95,2.85),.07)
    m.box('FreightRoof',(6.10,0,4.34),(3.45,3.1,.14),.03)
    m.box('VehicleGray',(8.35,0,2.05),(1.65,2.05,1.25),.05)
    for sy in (-1,1):
        m.box('VehicleGlass',(6.05,sy*1.485,3.45),(2.10,.025,.83))
        m.box('VehicleGlass',(7.735,sy*.74,3.50),(.025,1.15,.78))
        for z in (1.7,2.2,2.7):m.branch('VehicleMetal',(-9.2,sy*1.44,z),(4.3,sy*1.44,z),.024,.024,6)
        for x in (-9.1,-5.4,-1.7,2.,4.2):m.branch('VehicleMetal',(x,sy*1.44,1.45),(x,sy*1.44,2.70),.025,.025,6)
        for x in (-7,-5,-3,-1):m.box('VehicleDark',(x,sy*1.033,3.1),(1.1,.025,.9))
        for x in (-9.1,9.1):
            for step,z in enumerate((.50,.80,1.10)):m.box('VehicleMetal',(x,sy*(1.40-step*.10),z),(.55,.45,.10))
    for x in (-6.3,6.3):
        m.box('VehicleDark',(x,0,.87),(3.45,2.05,.44))
        for ax in (x-.90,x+.90):
            m.branch('VehicleMetal',(ax,-.90,.48),(ax,.90,.48),.085,.085,8)
            for y in (-.7625,.7625):wheel(m,ax,y,.48,.48,.16,1,True)
    for x in (-9.85,9.85):
        m.box('VehicleDark',(x,0,.86),(1.10,.32,.24))
        m.box('VehicleMetal',(x+math.copysign(.40,x),0,.86),(.26,.45,.26))
    for y in (-.55,.55):m.box('ReflectWhite',(9.19,y,2.45),(.03,.25,.18))
    return m,dict(kind='diesel_locomotive',front_axis='+X',ground_origin=True,
                  rail_contact_z_m=0.,coupler_x_m=[-10.38,10.38],bogie_centers_x_m=[-6.3,6.3],
                  collision_body_bounds_m=[[-9.5,9.5],[-1.55,1.55],[.81,4.41]],
                  wheel_radius_m=.48,wheel_axis_gauge_m=1.525,estimated_dimensions=True,
                  policy='Generic neutral low-poly yard locomotive; no invented operator branding')
