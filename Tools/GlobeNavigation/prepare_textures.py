"""Build stylized, geographically faithful globe maps from Natural Earth and NASA GEBCO."""
from pathlib import Path
import json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GlobeNavigation'
DATA=OUT/'Geodata'
TEX=OUT/'Textures'
TEX.mkdir(exist_ok=True)
W,H=4096,2048
features=json.loads((DATA/'countries.geojson').read_text(encoding='utf-8'))['features']
mask=Image.new('L',(W,H)); draw=ImageDraw.Draw(mask)
borders=Image.new('L',(W,H)); bd=ImageDraw.Draw(borders)
def xy(p): return ((p[0]+180)/360*W,(90-p[1])/180*H)
for feature in features:
 geom=feature['geometry']; polys=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
 for poly in polys:
  for idx,ring in enumerate(poly):
   pts=[xy(p) for p in ring]
   draw.polygon(pts,fill=255 if idx==0 else 0)
   bd.line(pts,fill=255,width=2)
def raster_layer(filename):
 im=Image.new('L',(W,H));d=ImageDraw.Draw(im)
 for f in json.loads((DATA/filename).read_text(encoding='utf-8'))['features']:
  g=f['geometry'];polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
  for poly in polys:
   for idx,ring in enumerate(poly):d.polygon([xy(p) for p in ring],fill=255 if idx==0 else 0)
 return np.asarray(im,dtype=np.float32)/255
lakes=raster_layer('lakes.geojson');ice=raster_layer('ice.geojson')
mask=Image.fromarray(np.uint8(np.asarray(mask)*(1-lakes)))
land=np.array(mask.filter(ImageFilter.GaussianBlur(.55)),dtype=np.float32)/255
source=next(DATA.rglob('NE1_50M_SR.tif'))
base=np.asarray(Image.open(source).convert('RGB').resize((W,H),Image.Resampling.LANCZOS),dtype=np.float32)/255
elev=np.asarray(Image.open(DATA/'elevation.jpg').convert('L').resize((W,H),Image.Resampling.LANCZOS),dtype=np.float32)/255
# Style the satellite-derived cover into the reference's green/beige atlas palette.
# The vegetation contrast comes from source chroma; physical relief remains NASA data.
vegetation=np.clip((base[:,:,1]-base[:,:,0])*16+.18,0,1)
green=np.array([.43,.58,.27]);sand=np.array([.76,.72,.55])
styled=sand*(1-vegetation[:,:,None])+green*vegetation[:,:,None]
lum=base.mean(axis=2)
smooth=np.asarray(Image.fromarray(np.uint8(lum*255)).filter(ImageFilter.GaussianBlur(4)),dtype=np.float32)/255
shade=np.clip(1+(lum-smooth)*2.8,.62,1.2)
styled*=shade[:,:,None]
snow=(base.min(axis=2)>.92)&(land>.3)
styled[snow]=np.array([.92,.95,.96])*shade[snow,None]
styled=styled*(1-ice[:,:,None])+np.array([.92,.95,.96])*shade[:,:,None]*ice[:,:,None]
base=styled
water=np.empty_like(base); water[:]=[.195,.365,.505]
color=water*(1-land[:,:,None])+base*land[:,:,None]
# Cartographic border and graticule are texture details, not thousands of draw calls.
edge=np.asarray(borders.filter(ImageFilter.GaussianBlur(.3)),dtype=np.float32)/255
color=color*(1-edge[:,:,None]*.37)+np.array([.89,.91,.78])*edge[:,:,None]*.37
grid=Image.new('L',(W,H)); gd=ImageDraw.Draw(grid)
for lon in range(-180,180,15): gd.line([xy((lon,-90)),xy((lon,90))],fill=255,width=1)
for lat in range(-75,90,15): gd.line([xy((-180,lat)),xy((180,lat))],fill=255,width=1)
grid=np.asarray(grid,dtype=np.float32)/255
alpha=grid*.13*(1-land*.65)
color=color*(1-alpha[:,:,None])+np.array([.71,.82,.86])*alpha[:,:,None]
Image.fromarray(np.uint8(np.clip(color,0,1)*255)).save(TEX/'T_Earth_BaseColor.png')
height=land*(.23+.77*elev)
Image.fromarray(np.uint8(np.clip(height,0,1)*255)).save(TEX/'T_Earth_Height.png')
# Tangent-space normal: detail uses GEBCO height, baked independently of the base color.
dx=(np.roll(height,-1,axis=1)-np.roll(height,1,axis=1))*.5
dy=(np.roll(height,-1,axis=0)-np.roll(height,1,axis=0))*.5
nx=-dx*26; ny=dy*26; nz=np.ones_like(nx)
norm=np.sqrt(nx*nx+ny*ny+nz*nz)
normal=np.stack([nx/norm,ny/norm,nz/norm],axis=-1)*.5+.5
Image.fromarray(np.uint8(normal*255)).save(TEX/'T_Earth_Normal_OpenGL.png')
normal[:,:,1]=1-normal[:,:,1]
Image.fromarray(np.uint8(normal*255)).save(TEX/'T_Earth_Normal_UE.png')
Image.fromarray(np.uint8((.58+.24*land)*255)).save(TEX/'T_Earth_Roughness.png')
mask.save(TEX/'T_Earth_LandMask.png')
# Store finite geographical values independently of the rendering/cartographic exaggeration.
geo=json.loads((DATA/'warehouse-arcgis.json').read_text())['candidates'][0]
osm=json.loads((DATA/'warehouse-osm.json').read_text()); nodes={x['id']:x for x in osm['elements'] if x['type']=='node'}
way=next(x for x in osm['elements'] if x['type']=='way'); ring=[(nodes[n]['lon'],nodes[n]['lat']) for n in way['nodes']]
x,y=geo['location']['x'],geo['location']['y']; inside=False
for a,b in zip(ring,ring[1:]):
 if (a[1]>y)!=(b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: inside=not inside
assert geo['score']==100 and geo['attributes']['Addr_type']=='PointAddress' and inside
point={'id':'ghs-ca-us','latitude':y,'longitude':x,'crs':'EPSG:4326','address':geo['address'],'geocoder':'Esri World Geocoding Service','matchType':'PointAddress','score':100,'insideOsmBuilding':inside,'osmWay':521644442,'note':'Address-level location validated inside matching OSM industrial building. Not a survey control point. Historical OSM tenant name is not asserted as current GHS tenant.'}
(OUT/'warehouse-location.json').write_text(json.dumps(point,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'textures':[str(p) for p in TEX.glob('*.png')],'warehouse':point},ensure_ascii=False))
