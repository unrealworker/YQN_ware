"""Independent float64 clearance of saved FBX triangle surfaces.

Ordinary Python + NumPy/Shapely only. No bpy, engine, external FBX reader, or
source generation functions. Blender roundtrip validation proves blend equality.
"""
from array import array
import hashlib,json,struct,sys,traceback,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
import shapely
from shapely import STRtree
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57'
OUTPUT=ROOT/'Saved/MPR/rebuild_20261104/surface_clearance.json'
REPORT=dict(success=False,method='Binary FBX + Shapely STRtree + float64 triangle planes',
    scope='Every saved triangle centroid and three edge midpoints; no native ray precision dependency',
    assets_saved=False,groups={},failures=[])
NUMERICAL_TOLERANCE_M=.00004
XY_BOUNDARY_TOLERANCE_M=.0002
MAX_FAILURE_DETAILS=60

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def fbx_nodes(path):
    """Minimal standard binary FBX reader, independent of Blender installation."""
    with path.open('rb') as stream:
        assert stream.read(23)==b'Kaydara FBX Binary  \x00\x1a\x00','Expected binary FBX'
        version=struct.unpack('<I',stream.read(4))[0]
        header='<QQQB' if version>=7500 else '<IIIB';size=struct.calcsize(header)
        scalar={'Y':'h','C':'?','I':'i','F':'f','D':'d','L':'q','Z':'b'}
        arrays={'f':'f','d':'d','i':'i','l':'q','b':'b','c':'B'}
        def value():
            code=stream.read(1).decode('ascii')
            if code in scalar:
                fmt='<'+scalar[code];return struct.unpack(fmt,stream.read(struct.calcsize(fmt)))[0]
            if code in {'S','R'}:
                length=struct.unpack('<I',stream.read(4))[0];return stream.read(length)
            if code in arrays:
                length,encoding,size=struct.unpack('<III',stream.read(12));payload=stream.read(size)
                assert encoding in {0,1}
                if encoding:payload=zlib.decompress(payload)
                result=array(arrays[code]);result.frombytes(payload)
                if sys.byteorder!='little':result.byteswap()
                assert len(result)==length
                return result
            raise ValueError('Unsupported FBX property '+code)
        def node():
            end,count,prop_bytes,name_size=struct.unpack(header,stream.read(size))
            if not end:return None
            name=stream.read(name_size);props=[value()for _ in range(count)];children=[]
            while stream.tell()<end:
                child=node()
                if child is None:break
                children.append(child)
            assert stream.tell()==end,(name,stream.tell(),end)
            return name,props,children
        result=[]
        while True:
            item=node()
            if item is None:break
            result.append(item)
        return result

def mesh_data(row):
    path=(ROOT/row['fbx']).resolve()
    assert path.is_relative_to(SOURCE.resolve()) and sha(path)==row['sha256']
    objects=next(n for n in fbx_nodes(path)if n[0]==b'Objects')
    geometries=[n for n in objects[2]if n[0]==b'Geometry'];assert len(geometries)==1
    fields={n[0]:n for n in geometries[0][2]}
    vertices=np.asarray(fields[b'Vertices'][1][0],dtype=np.float64).reshape(-1,3)
    # This exporter stores raw CAD metres. Native roundtrip checks model-axis metadata.
    bounds=np.stack((vertices.min(0),vertices.max(0)),axis=1)
    assert np.max(np.abs(bounds-np.asarray(row['bounds_m'])))<.02,row['name']
    raw=np.asarray(fields[b'PolygonVertexIndex'][1][0],dtype=np.int64)
    faces=[];corners=[];current=[]
    for corner,index in enumerate(raw):
        current.append((int(index)if index>=0 else int(-index-1),corner))
        if index<0:
            for i in range(1,len(current)-1):
                tri=(current[0],current[i],current[i+1]);faces.append(tuple(p[0]for p in tri));corners.append(tuple(p[1]for p in tri))
            current=[]
    faces=np.asarray(faces,dtype=np.int64);assert len(faces)==row['triangles']
    colors_by_corner=np.zeros(len(raw),dtype=np.float64)
    for layer in [n for n in geometries[0][2]if n[0]==b'LayerElementColor']:
        vals={n[0]:n[1][0]for n in layer[2]}
        if vals.get(b'Name')!=b'EdgeFade':continue
        colors=np.asarray(vals[b'Colors'],dtype=np.float64).reshape(-1,4)[:,0]
        ref=vals[b'ReferenceInformationType'];mapping=vals[b'MappingInformationType']
        assert ref in {b'Direct',b'IndexToDirect'}
        direct=colors[np.asarray(vals[b'ColorIndex'],dtype=np.int64)]if ref==b'IndexToDirect'else colors
        if mapping==b'ByPolygonVertex':colors_by_corner=direct
        elif mapping in {b'ByVertice',b'ByVertex'}:colors_by_corner=direct[np.where(raw>=0,raw,-raw-1)]
        else:raise AssertionError('Unsupported color mapping '+str(mapping))
    return vertices[faces],colors_by_corner[np.asarray(corners,dtype=np.int64)]

class TriangleSurface:
    def __init__(self,rows):
        triangles=np.concatenate([mesh_data(row)[0]for row in rows])
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        valid=np.abs(normals[:,2])>1e-10
        self.triangles,self.normals=triangles[valid],normals[valid]
        self.shapes=shapely.polygons(self.triangles[:,:,:2]);self.index=STRtree(self.shapes)
    def heights(self,points):
        locations=shapely.points(points[:,:2]);pairs=self.index.query(locations,predicate='intersects')
        heights=np.full(len(points),-np.inf);recovered=np.zeros(len(points),dtype=bool)
        def evaluate(indices,triangle_indices):
            origins=self.triangles[triangle_indices,0];normals=self.normals[triangle_indices]
            xy=points[indices,:2]-origins[:,:2]
            z=origins[:,2]-(xy[:,0]*normals[:,0]+xy[:,1]*normals[:,1])/normals[:,2]
            np.maximum.at(heights,indices,z)
        if pairs.size:evaluate(pairs[0],pairs[1])
        missing=np.flatnonzero(~np.isfinite(heights))
        if len(missing):
            near=self.index.query(locations[missing],predicate='dwithin',distance=XY_BOUNDARY_TOLERANCE_M)
            if near.size:
                recovered[missing[near[0]]]=True;evaluate(missing[near[0]],near[1])
        heights[~np.isfinite(heights)]=np.nan
        return heights,recovered

def inspect(rows,reference,category,minimum_clearance,crossing_surface=None):
    group=dict(objects=len(rows),triangles=0,samples=0,opaque_samples=0,outer_fade_samples=0,
        covered_by_crossing_samples=0,missing_reference_samples=0,boundary_tolerance_samples=0,
        minimum_opaque_clearance_m=None,minimum_outer_clearance_m=None,failures=0,worst_samples=[])
    assert rows
    weights=np.asarray(((1/3,1/3,1/3),(.5,.5,0.),(0.,.5,.5),(.5,0.,.5)))
    labels=['centroid','edge01','edge12','edge20'];worst=[]
    for row in rows:
        triangles,colors=mesh_data(row);normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        valid=np.flatnonzero(np.abs(normals[:,2])>1e-10)
        points=np.einsum('sk,tkd->tsd',weights,triangles[valid]).reshape(-1,3)
        fades=np.einsum('sk,tk->ts',weights,colors[valid]).reshape(-1)
        group['triangles']+=len(triangles);group['samples']+=len(points)
        heights,recovered=reference.heights(points);covered=np.zeros(len(points),dtype=bool)
        if crossing_surface is not None:
            deck,_=crossing_surface.heights(points);covered=np.isfinite(deck)&(deck>points[:,2]+.001)
        active=~covered;missing=active&~np.isfinite(heights);clearance=points[:,2]-heights
        opaque=(fades<=.02)&active&~missing;outer=(fades>.02)&active&~missing
        thresholds=np.where(fades<=.02,minimum_clearance,minimum_clearance*np.maximum(.01,1-.99*fades))
        failed=missing|(active&~missing&(clearance+NUMERICAL_TOLERANCE_M<thresholds))
        group['covered_by_crossing_samples']+=int(covered.sum());group['missing_reference_samples']+=int(missing.sum())
        group['boundary_tolerance_samples']+=int((active&recovered).sum())
        group['opaque_samples']+=int(opaque.sum());group['outer_fade_samples']+=int(outer.sum());group['failures']+=int(failed.sum())
        for mask,key in [(opaque,'minimum_opaque_clearance_m'),(outer,'minimum_outer_clearance_m')]:
            if np.any(mask):
                v=float(clearance[mask].min());group[key]=v if group[key]is None else min(group[key],v)
        def record(index):
            result=dict(mesh=row['name'],triangle=int(valid[index//4]),sample=labels[index%4],
                xyz_m=points[index].tolist(),fade=float(fades[index]),threshold_m=float(thresholds[index]),
                boundary_tolerance_used=bool(recovered[index]))
            if missing[index]:result['reason']='No reference triangle within 0.2mm XY tolerance'
            else:result['clearance_m']=float(clearance[index])
            return result
        for index in np.flatnonzero(failed)[:max(0,MAX_FAILURE_DETAILS-len(REPORT['failures']))]:
            REPORT['failures'].append(dict(category=category,**record(index)))
        candidates=np.flatnonzero(active&~missing)
        if len(candidates):
            candidates=candidates[np.argsort((clearance-thresholds)[candidates])[:20]]
            worst.extend(record(i)for i in candidates);worst=sorted(worst,key=lambda x:x['clearance_m']-x['threshold_m'])[:20]
    group['worst_samples']=worst;REPORT['groups'][category]=group
    print('MPR_CLEARANCE_GROUP',category,group['samples'],group['failures'],flush=True)
    return group['failures']

def main():
    manifest_path=SOURCE/'manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    blend=(ROOT/manifest['blend']).resolve();assert blend.is_relative_to(SOURCE.resolve()) and blend.is_file()
    before,manifest_before=sha(blend),sha(manifest_path)
    REPORT.update(blend_sha256=before,manifest_sha256=manifest_before,numeric_tolerance_m=NUMERICAL_TOLERANCE_M,
        xy_boundary_tolerance_m=XY_BOUNDARY_TOLERANCE_M,threshold_opaque_road_terrain_m=.06,threshold_opaque_paint_road_m=.015)
    def starts(prefixes):return[r for r in manifest['meshes']if r['name'].startswith(prefixes)]
    terrain=TriangleSurface(starts(('SM_MPRR_Terrain','SM_MPRR_Background')))
    roads=starts('SM_MPRR_Roads_');road_surface=TriangleSurface(roads)
    crossings=TriangleSurface(starts(('SM_MPRR_CrossingDeck','SM_MPRR_CrossingRamp')))
    failures=inspect(roads,terrain,'asphalt_over_actual_terrain',.06)
    failures+=inspect(starts('SM_MPRR_WhiteEdges_'),road_surface,'white_edges_over_actual_asphalt',.015,crossings)
    failures+=inspect(starts('SM_MPRR_RoadDashes_'),road_surface,'dashes_over_actual_asphalt',.015,crossings)
    REPORT.update(success=failures==0,failure_sample_count=failures,
        blend_unchanged=sha(blend)==before,manifest_unchanged=sha(manifest_path)==manifest_before)
    assert REPORT['blend_unchanged'] and REPORT['manifest_unchanged'],'Read-only source bytes changed during verification'
    assert not failures,f'{failures} surface clearance samples failed; see {OUTPUT}'

if __name__=='__main__':
    try:main()
    except Exception:
        REPORT['success']=False;REPORT['error']=traceback.format_exc();raise
    finally:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf8')
        print('MPR_REBUILD_SURFACE_CLEARANCE',json.dumps({k:v for k,v in REPORT.items()if k not in ('groups','failures')},ensure_ascii=False))
