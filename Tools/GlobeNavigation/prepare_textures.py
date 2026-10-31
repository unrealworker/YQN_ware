"""Build geographic maps from native Natural Earth and NASA GEBCO sources."""
from pathlib import Path
import gc
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GlobeNavigation'
DATA=OUT/'Geodata'
TEX=OUT/'Textures'
TEX.mkdir(exist_ok=True)
COLOR_SIZE=(8192,4096)
PHYSICAL_SIZE=(4096,2048)
OCEAN_SRGB=(.145,.30,.43)
features=json.loads((DATA/'countries.geojson').read_text(encoding='utf-8'))['features']

def xy(p,size):
    return ((p[0]+180)/360*size[0],(90-p[1])/180*size[1])

def geographic_mask(records,size,borders=None):
    mask=Image.new('L',size);draw=ImageDraw.Draw(mask)
    border_draw=ImageDraw.Draw(borders) if borders is not None else None
    for feature in records:
        geom=feature['geometry']
        polygons=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
        for polygon in polygons:
            for index,ring in enumerate(polygon):
                points=[xy(p,size) for p in ring]
                draw.polygon(points,fill=255 if index==0 else 0)
                if border_draw:
                    border_draw.line(points,fill=255,width=max(1,round(2*size[0]/4096)))
    return mask

def layer(filename,size):
    records=json.loads((DATA/filename).read_text(encoding='utf-8'))['features']
    return np.asarray(geographic_mask(records,size),dtype=np.float32)/255

def land_layers(size,with_borders=False):
    borders=Image.new('L',size) if with_borders else None
    mask=geographic_mask(features,size,borders)
    lakes=layer('lakes.geojson',size)
    mask=Image.fromarray(np.uint8(np.asarray(mask)*(1-lakes)))
    land=np.asarray(mask.filter(ImageFilter.GaussianBlur(.55*size[0]/4096)),dtype=np.float32)/255
    return mask,land,borders

def build_physical_maps():
    # Retain established 4K height and normal scale, matching existing geometry.
    # The 5400x2700 GEBCO source contains no genuine 8K elevation detail.
    mask,land,_=land_layers(PHYSICAL_SIZE)
    elevation=np.asarray(Image.open(DATA/'elevation.jpg').convert('L').resize(PHYSICAL_SIZE,Image.Resampling.LANCZOS),dtype=np.float32)/255
    height=land*(.23+.77*elevation)
    Image.fromarray(np.uint8(np.clip(height,0,1)*255)).save(TEX/'T_Earth_Height.png')
    dx=(np.roll(height,-1,axis=1)-np.roll(height,1,axis=1))*.5
    dy=(np.roll(height,-1,axis=0)-np.roll(height,1,axis=0))*.5
    nx,ny=-dx*26,dy*26
    magnitude=np.sqrt(nx*nx+ny*ny+1)
    normal=np.stack([nx/magnitude,ny/magnitude,1/magnitude],axis=-1)*.5+.5
    Image.fromarray(np.uint8(normal*255)).save(TEX/'T_Earth_Normal_OpenGL.png')
    normal[:,:,1]=1-normal[:,:,1]
    Image.fromarray(np.uint8(normal*255)).save(TEX/'T_Earth_Normal_UE.png')
    Image.fromarray(np.uint8((.58+.24*land)*255)).save(TEX/'T_Earth_Roughness.png')
    mask.save(TEX/'T_Earth_LandMask.png')

def build_color_map():
    size=COLOR_SIZE
    _,land,borders=land_layers(size,with_borders=True)
    source=next(DATA.rglob('NE1_50M_SR.tif'))
    original=Image.open(source)
    if original.width<size[0] or original.height<size[1]:
        raise ValueError('Color source must have at least the requested native resolution')
    source_size=original.size
    base=np.asarray(original.convert('RGB').resize(size,Image.Resampling.LANCZOS),dtype=np.float32)/255
    # Chroma and relief shading come directly from spatially registered real data.
    vegetation=np.clip((base[:,:,1]-base[:,:,0])*16+.18,0,1)
    luminance=base.mean(axis=2)
    snow=(base.min(axis=2)>.92)&(land>.3)
    del base
    green=np.array([.43,.58,.27],dtype=np.float32)
    sand=np.array([.76,.72,.55],dtype=np.float32)
    color=sand+(green-sand)*vegetation[:,:,None]
    del vegetation
    smooth=np.asarray(Image.fromarray(np.uint8(luminance*255)).filter(ImageFilter.GaussianBlur(4*size[0]/4096)),dtype=np.float32)/255
    shade=np.clip(1+(luminance-smooth)*2.8,.62,1.2)
    del luminance,smooth
    color*=shade[:,:,None]
    snow_color=np.array([.92,.95,.96],dtype=np.float32)
    color[snow]=snow_color*shade[snow,None]
    del snow
    ice=layer('ice.geojson',size)
    color*=1-ice[:,:,None]
    color+=snow_color*shade[:,:,None]*ice[:,:,None]
    del ice,shade
    color*=land[:,:,None]
    color+=np.array(OCEAN_SRGB,dtype=np.float32)*(1-land[:,:,None])
    # Keep angular line weights unchanged when doubling output resolution.
    edge=np.asarray(borders.filter(ImageFilter.GaussianBlur(.3*size[0]/4096)),dtype=np.float32)/255
    color*=1-edge[:,:,None]*.37
    color+=np.array([.89,.91,.78],dtype=np.float32)*edge[:,:,None]*.37
    del borders,edge
    grid=Image.new('L',size);draw=ImageDraw.Draw(grid)
    width=max(1,round(size[0]/4096))
    for lon in range(-180,180,15):
        draw.line([xy((lon,-90),size),xy((lon,90),size)],fill=255,width=width)
    for lat in range(-75,90,15):
        draw.line([xy((-180,lat),size),xy((180,lat),size)],fill=255,width=width)
    alpha=np.asarray(grid,dtype=np.float32)/255*.13*(1-land*.65)
    color*=1-alpha[:,:,None]
    color+=np.array([.71,.82,.86],dtype=np.float32)*alpha[:,:,None]
    Image.fromarray(np.uint8(np.clip(color,0,1)*255)).save(TEX/'T_Earth_BaseColor.png')
    return source,source_size

build_physical_maps()
gc.collect()
source,source_size=build_color_map()
gc.collect()
# Coordinates stay independent from rendering/cartographic exaggeration.
geo=json.loads((DATA/'warehouse-arcgis.json').read_text())['candidates'][0]
osm=json.loads((DATA/'warehouse-osm.json').read_text())
nodes={x['id']:x for x in osm['elements'] if x['type']=='node'}
way=next(x for x in osm['elements'] if x['type']=='way')
ring=[(nodes[n]['lon'],nodes[n]['lat']) for n in way['nodes']]
x,y=geo['location']['x'],geo['location']['y'];inside=False
for a,b in zip(ring,ring[1:]):
    if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
        inside=not inside
assert geo['score']==100 and geo['attributes']['Addr_type']=='PointAddress' and inside
point={'id':'ghs-ca-us','latitude':y,'longitude':x,'crs':'EPSG:4326','address':geo['address'],'geocoder':'Esri World Geocoding Service','matchType':'PointAddress','score':100,'insideOsmBuilding':inside,'osmWay':521644442,'note':'Address-level location validated inside matching OSM industrial building. Not a survey control point. Historical OSM tenant name is not asserted as current GHS tenant.'}
(OUT/'warehouse-location.json').write_text(json.dumps(point,ensure_ascii=False,indent=2),encoding='utf-8')
report={'colorSource':str(source.relative_to(OUT)),'colorSourceSize':source_size,'colorOutputSize':COLOR_SIZE,'elevationSourceSize':[5400,2700],'physicalOutputSize':PHYSICAL_SIZE,'oceanSrgb':OCEAN_SRGB,'runtime':{'colorCompression':'BC7','colorMaxSize':8192,'colorMipGeneration':'Sharpen2','normalCompression':'BC5','normalMaxSize':4096,'roughnessMaxSize':2048},'colorFullMipMemoryMiB':round(COLOR_SIZE[0]*COLOR_SIZE[1]*4/3/1024/1024,2),'geographicGeometryRegenerated':False}
(OUT/'texture-build-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'textureBuild':report,'warehouse':point},ensure_ascii=False))
