"""CAD footprint-specific supply belts and flush crossed floor placeholders.

XY boundaries are measured. Z values are a clearly labelled display profile,
not commissioned equipment elevations or evidence of a connected line.
"""
import math
MARKER_MESH='SM_MPR_CADFloorPlaceholder'
def slope_slab(g,n,role,x0,x1,y0,y1,z0,z1,thickness):
    vs=[(x0,y0,z0),(x1,y0,z1),(x1,y1,z1),(x0,y1,z0)]
    g.mesh(n,role,vs+[(x,y,z-thickness) for x,y,z in vs],[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
def add_meshes(g,evidence):
    # Preserve the original rectangle and both diagonals; do not invent a table.
    corners=[(-.5,-.6),(.5,-.6),(.5,.6),(-.5,.6)]
    for a,b in zip(corners,corners[1:]+corners[:1]):g.segment(MARKER_MESH,'Charcoal',a,b,.012,.012,.004)
    for a,b in [(corners[0],corners[2]),(corners[1],corners[3])]:g.segment(MARKER_MESH,'Charcoal',a,b,.008,.012,.004)
    specs={}
    for row in evidence['ramps']:
        h=row['source_handle'];pos=row['placement']['position_m'];name='SM_MPR_CADSupplyBelt_'+h
        ps=[p for q in row['primitives'] for p in q['points_cad_m']]
        lo=[min(p[i] for p in ps) for i in (0,1)];hi=[max(p[i] for p in ps) for i in (0,1)]
        # The actual transporting strip is narrower than the guide/motor envelope.
        if h=='2E7F10':
            belt=next(p for p in row['primitives'] if p['source_handles'][-1]=='2E7CE9')['points_cad_m']
            x0,x1=min(p[0] for p in belt),max(p[0] for p in belt)
            y0,y1=min(p[1] for p in belt),max(p[1] for p in belt)
            belt_source=['2E7CE9'];zstart,zend=1.0,.74
        else:
            # Parallel 586 mm strip boundaries and transverse end boundaries.
            edge=next(p for p in row['primitives'] if p['source_handles'][-1]=='1E2EE4')['points_cad_m']
            edge2=next(p for p in row['primitives'] if p['source_handles'][-1]=='1E2F21')['points_cad_m']
            y0,y1=sorted([edge[0][1],edge2[0][1]])
            x0,x1=lo[0]+.016,hi[0]-.016
            belt_source=['1E2EE4','1E2F21','1E2ED9','1E2F0F'];zstart,zend=(.74,1.0) if h=='2CCF62' else (1.0,.74)
        # All three CAD supply belts travel on world CAD X. The old reuse mapped
        # the X-long 2E7F10 to mesh width and therefore rotated the roller logic.
        x0-=pos[0];x1-=pos[0];y0-=pos[1];y1-=pos[1]
        def height(x):return zstart+(zend-zstart)*(x-x0)/(x1-x0)
        slope_slab(g,name,'Rubber',x0,x1,y0,y1,zstart,zend,.045)
        # Narrow frame rails follow the measured belt, not the full bounding box.
        for y in (y0-.025,y1+.025):slope_slab(g,name,'Cobalt',x0,x1,y-.022,y+.022,zstart+.07,zend+.07,.13)
        for x in (x0+.15,x1-.15):
            z=height(x)-.08
            for y in (y0+.04,y1-.04):
                g.box(name,'Metal',(x,y,z/2),(.045,.045,z))
                g.box(name,'Charcoal',(x,y,.025),(.10,.10,.05))
            g.box(name,'Metal',(x,(y0+y1)/2,.22),(.035,y1-y0-.08,.035))
            if h in ('2CCF62','2CCF66'):
                # A head beam overlaps both leg tops and the belt/frame bottom;
                # the support must remain attached in low-angle close views.
                g.box(name,'Metal',(x,(y0+y1)/2,height(x)-.075),(.09,y1-y0+.11,.12))
        # Original outer guide geometry, simplified only in vertical detail.
        # Retain the source XY extent as side guards, not a full-envelope deck.
        outer_guides={}
        for q in row['primitives']:
            if q['type']!='LINE':continue
            a,b=q['points_cad_m'][0],q['points_cad_m'][-1]
            if math.dist(a,b)<.7:continue
            if abs(a[1]-b[1])>.0001:continue
            if min(abs(a[1]-(y0+pos[1])),abs(a[1]-(y1+pos[1])))<.08:continue
            ax,bx=a[0]-pos[0],b[0]-pos[0];ay=a[1]-pos[1]
            side=-1 if ay<(y0+y1)/2 else 1
            previous=outer_guides.get(side)
            if previous is None or side*ay>side*previous[2]:outer_guides[side]=(min(ax,bx),max(ax,bx),ay)
        for side,(ax,bx,ay) in outer_guides.items():
            inner=y0+.003 if side<0 else y1-.003
            outer=ay+side*.008
            # Fill the entire measured side cheek up to the main-frame top.
            # A low silver tray under a separate blue bar was structurally
            # touching but still read as floating in the actual UE close view.
            # This single blue solid overlaps the inner frame and reaches the
            # same source outer edge, with visible transverse brackets below.
            slope_slab(g,name,'Cobalt',ax,bx,min(inner,outer),max(inner,outer),height(ax)+.07,height(bx)+.07,.15)
            brace_inner=y0+.06 if side<0 else y1-.06
            for x in (ax+.08,bx-.08):
                g.box(name,'Metal',(x,(brace_inner+outer)/2,height(x)-.085),
                      (.06,abs(outer-brace_inner),.08))
        if h=='2E7F10':
            # Motor housing is indicated beside the measured belt; it is not
            # another broad conveyor surface across the CAD envelope.
            bx=lo[0]-pos[0];ex=x0
            g.box(name,'Cobalt',((bx+ex)/2,(y0+y1)/2,.81),(max(.05,ex-bx),y1-y0,.18))
        specs[h]={'mesh':name,'position_m':[*pos,0],'rotation_deg':0,'scale':[1,1,1],'source_handles':[h],
                  'kind':'cad_supply_belt','belt_boundary_source_handles':belt_source,
                  'belt_endpoints_cad_m':[[x0+pos[0],(y0+y1)/2+pos[1],zstart],[x1+pos[0],(y0+y1)/2+pos[1],zend]],
                  'source_xy_bounds_m':[lo,hi],'height_basis':'display-only 0.74m to 1.0m; source CAD has no validated elevation','flow_basis':'unconfirmed; no connected upstream/downstream inferred','collision':False,'tick':False}
    return specs
