"""CAD-edge-derived V rollers for the three recovered U33 feed lines."""
import math


def _local(point, reference, mirrored):
    # Reference source flows toward CAD +X; its mesh's long axis is local +Y.
    dx=point[0]-reference['reference_position_m'][0]
    dy=point[1]-reference['reference_position_m'][1]
    return (dy if mirrored else -dy,dx)


def _roller(g,name,edges,diameter,top):
    radius=diameter/2
    sides=8
    vertices=[]
    for end in (0,1):
        a,b=edges[0][end],edges[1][end]
        center=[(a[k]+b[k])/2 for k in range(2)]
        half=[(b[k]-a[k])/2 for k in range(2)]
        for i in range(sides):
            angle=i*2*math.pi/sides
            # CAD clips some end rollers obliquely. Interpolate between the
            # two measured edge ends so a square-ended cylinder cannot protrude
            # through the side frame by averaging the unequal edge lengths.
            vertices.append((center[0]+half[0]*math.cos(angle),
                             center[1]+half[1]*math.cos(angle),
                             top-radius+radius*math.sin(angle)))
    faces=[tuple(range(sides-1,-1,-1)),tuple(range(sides,sides*2))]
    faces.extend((i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides))
    centroid=[sum(v[k] for v in vertices)/len(vertices) for k in range(3)]
    oriented=[]
    for face in faces:
        a,b,c=[vertices[i] for i in face[:3]]
        ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)]
        normal=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
        midpoint=[sum(vertices[i][k] for i in face)/len(face) for k in range(3)]
        oriented.append(tuple(reversed(face)) if sum(normal[k]*(midpoint[k]-centroid[k]) for k in range(3))<0 else face)
    g.mesh(name,'Metal',vertices,oriented)


def add_chevron_meshes(g,evidence):
    """Return per-feed mesh specs; preserve full signed CAD plan geometry.

    Roller diameter and lateral footprint come from paired source edges. The
    end rings follow their clipped edge endpoints; the radial section, frame
    thickness and supports remain display approximations.
    """
    reference=evidence['chevron_reference']
    assert len(reference['rollers'])==34
    result={}
    for row in evidence['feeds']:
        if row['mesh_key']!='chevron':
            continue
        name='SM_MPR_CADFeedChevron_'+row['curve_handle']
        width,length=row['size_m']
        assert row['port_heights_m']==[1.5,1.5]
        mirrored=row['rotation_deg']>0
        assert abs(abs(row['rotation_deg'])-90)<1e-5
        for roller in reference['rollers']:
            edges=[[_local(p,reference,mirrored) for p in edge]
                   for edge in roller['source_edge_segments_m']]
            _roller(g,name,edges,roller['diameter_m'],1.5)
        # Continuous side frames sit below the bearing crown; transfer ends
        # remain open. No rectangle is substituted for the V-shaped rollers.
        for x in (-width/2+.008,width/2-.008):
            g.box(name,'Cobalt',(x,0,1.43),(.016,length,.10))
            for y in (-length*.37,length*.37):
                px=x-math.copysign(.04,x)
                g.box(name,'Metal',(px,y,.67),(.045,.045,1.34))
                g.box(name,'Charcoal',(px,y,.025),(.08,.08,.05))
        for y in (-length*.37,length*.37):
            g.box(name,'Metal',(0,y,1.34),(width-.09,.04,.04))
        result[row['id']]={'mesh':name,'native_size_m':row['size_m'],
                           'roller_count':34,'diameter_m':.05,
                           'surface_height_m':1.5,'source_parent':'2CC719',
                           'mirror_baked_into_vertices':mirrored}
    assert len(result)==3
    return result
