"""Download public, attributed cartography for the globe; no credentials required."""
from pathlib import Path
import concurrent.futures, json, urllib.request, urllib.parse, hashlib, zipfile, os

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GlobeNavigation/Geodata'
OUT.mkdir(parents=True, exist_ok=True)
PROXY = os.environ.get('GHS_GLOBE_HTTPS_PROXY','http://127.0.0.1:7897')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({'https':PROXY} if PROXY else {}))
SOURCES = {
 'lakes.geojson': 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson',
 'ice.geojson': 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_glaciated_areas.geojson',
 'natural-earth-landcover.zip': 'https://naciscdn.org/naturalearth/50m/raster/NE1_50M_SR.zip',
 'countries.geojson': 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson',
 'elevation.jpg':'https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/topography/gebco_08_rev_elev_5400x2700.jpg',
 'warehouse-osm.json':'https://api.openstreetmap.org/api/0.6/way/521644442/full.json',
 'warehouse-arcgis.json':'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?' + urllib.parse.urlencode({'SingleLine':'17335 Glen Helen Pkwy, San Bernardino, CA 92407','f':'pjson','outFields':'Match_addr,Addr_type,Score,DisplayX,DisplayY'})
}
def fetch(item):
 name,url = item
 path=OUT/name
 if not path.exists():
  with OPENER.open(urllib.request.Request(url,headers={'User-Agent':'GHS-GlobeNavigation-asset-build/1.0'}),timeout=60) as r:
   data=r.read()
  path.write_bytes(data)
 data=path.read_bytes()
 result={'file':name,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 print(json.dumps(result),flush=True)
 if name.endswith('.zip'):
  with zipfile.ZipFile(path) as z:
   for entry in z.infolist():
    dest=(OUT/entry.filename).resolve()
    if not dest.is_relative_to(OUT.resolve()): raise ValueError('Unsafe archive path')
   z.extractall(OUT)
 return result
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(fetch,SOURCES.items()))
 (OUT/'sources.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
