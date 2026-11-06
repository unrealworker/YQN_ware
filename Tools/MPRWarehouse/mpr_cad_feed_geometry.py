"""Recover measured feed-line surfaces; endpoint heights are display estimates.

The CAD labels constrain height ranges. The first two ramps use 1.0 -> 1.2
and 1.2 -> 1.5 m to meet the retained curve and H:1500 equipment. These are
explicit endpoint interpretations, not elevations measured from a 3D drawing.
"""
import math


def _slab(g, name, role, width, length, heights, thickness, offset=0):
    a, b = heights
    vertices = [(x, y, z + offset - dz) for dz in (thickness, 0)
                for x, y, z in [(-width/2, -length/2, a),
                                (width/2, -length/2, a),
                                (width/2, length/2, b),
                                (-width/2, length/2, b)]]
    g.mesh(name, role, vertices, [(0,3,2,1),(4,5,6,7),
                                (0,1,5,4),(1,2,6,5),
                                (2,3,7,6),(3,0,4,7)])


def _legs(g, name, width, length, heights):
    for y in (-length*.34, length*.34):
        fraction = (y+length/2)/length
        top = heights[0]+fraction*(heights[1]-heights[0])-.07
        for x in (-width*.37, width*.37):
            g.box(name,'Metal',(x,y,top/2),(.04,.04,top))
            g.box(name,'Rubber',(x,y,.015),(.08,.08,.03))
        g.box(name,'Metal',(0,y,.25),(width*.74,.035,.035))


def _belt(g,name,outer,inner,length,heights):
    _slab(g,name,'Metal',outer,length,heights,.055,-.025)
    _slab(g,name,'Rubber',inner,length,heights,.025)
    rail = (outer-inner)/2
    for side in (-1,1):
        # Match the sloped carrying surface without rotating legs off the floor.
        before = len(g.data[name]['Cobalt'][0])
        _slab(g,name,'Cobalt',rail,length,heights,.07,.05)
        vertices = g.data[name]['Cobalt'][0]
        for i in range(before,len(vertices)):
            x,y,z=vertices[i]
            vertices[i]=(x+side*(inner+rail)/2,y,z)
    _legs(g,name,outer,length,heights)


def _local(point,feed):
    angle=math.radians(-feed['rotation_deg'])
    x,y=[point[k]-feed['position_m'][k] for k in range(2)]
    return (math.cos(angle)*x-math.sin(angle)*y,
            math.sin(angle)*x+math.cos(angle)*y)


def add_feed_meshes(g,evidence):
    specs={}
    profiles={
        'rise120':('SM_MPR_CADFeedRise120',.86038,.79983,2.8,(1.,1.2)),
        'rise150':('SM_MPR_CADFeedRise150',.88,.8,2.19,(1.2,1.5)),
        'belt':('SM_MPR_CADFeedBelt',.88,.8,1.,(1.5,1.5)),
        'terminal':('SM_MPR_CADFeedTerminal',.415,.35,2.38,(1.5,1.5)),
    }
    for key,(name,outer,inner,length,heights) in profiles.items():
        _belt(g,name,outer,inner,length,heights)
    cap='SM_MPR_CADFeedCap'
    _slab(g,cap,'Metal',.795,1.,(1.5,1.5),.045)
    _legs(g,cap,.795,1.,(1.5,1.5))
    bay='SM_MPR_CADFeedTerminalBay'
    _slab(g,bay,'Metal',.81,1.,(1.5,1.5),.045)
    _legs(g,bay,.81,1.,(1.5,1.5))
    for feed in evidence['feeds']:
        key=feed['mesh_key']
        if key in profiles:
            name,outer,inner,length,heights=profiles[key]
            specs[feed['id']]={'mesh':name,'native_size_m':[outer,length]}
        elif key=='cap':
            specs[feed['id']]={'mesh':cap,'native_size_m':[.795,1.]}
        elif key=='bay':
            specs[feed['id']]={'mesh':bay,'native_size_m':[.81,1.]}
        elif key=='transfer':
            # The source crossed frame overlaps the next machine. Its exposed
            # transfer surface is clipped to the actual inter-machine interval.
            name='SM_MPR_CADFeedTransfer_'+feed['curve_handle']
            points=[_local(p,feed) for p in feed['render_polygon_m']]
            g.prism(name,'Metal',points,1.175,1.2)
            specs[feed['id']]={'mesh':name,'native_size_m':feed['size_m']}
        elif key!='chevron':
            raise ValueError('Unsupported CAD feed type: '+key)
    specs['__terminal__']={'mesh':profiles['terminal'][0],'native_size_m':[.415,2.38]}
    if any(f['mesh_key']=='chevron' for f in evidence['feeds']):
        from mpr_cad_feed_chevron_geometry import add_chevron_meshes
        specs.update(add_chevron_meshes(g,evidence))
    assert all(feed['id'] in specs for feed in evidence['feeds'])
    return specs
