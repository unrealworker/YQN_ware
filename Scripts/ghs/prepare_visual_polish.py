"""Bake a compact world-space campus mask; no Unreal or scene mutations."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Scripts/_vendor/cad'))
from shapely.geometry import Polygon

OUT = ROOT/'SourceAssets/GHS/VisualPolish'
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((ROOT/'SourceAssets/GHS/Park/park_manifest.json').read_text(encoding='utf-8-sig'))
original = Polygon(manifest['campus_boundary_uv_m'])
polygon = original.simplify(.25, preserve_topology=True)
assert polygon.is_valid and polygon.hausdorff_distance(original) < .26
points = list(polygon.exterior.coords)
resolution = 2048
bounds = [-450., -450., 950., 750.]
x = np.linspace(bounds[0], bounds[2], resolution, dtype=np.float32)[None, :]
y = np.linspace(bounds[1], bounds[3], resolution, dtype=np.float32)[:, None]
distance2 = np.full((resolution,resolution), np.inf, np.float32)
inside = np.zeros((resolution,resolution), bool)
for a,b in zip(points, points[1:]):
    dx,dy = b[0]-a[0], b[1]-a[1]
    t = np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy), 0, 1)
    distance2 = np.minimum(distance2, (x-a[0]-t*dx)**2+(y-a[1]-t*dy)**2)
    if abs(dy) > 1e-9:
        inside ^= ((y>a[1]) != (y>b[1])) & (x < a[0]+(y-a[1])*dx/dy)
distance = np.sqrt(distance2)
signed = np.where(inside, -distance, distance)
smooth = lambda t: np.clip(t,0,1)**2*(3-2*np.clip(t,0,1))
coverage = 1-smooth((signed+.42)/.84)
green = smooth((signed-12)/58)
border = (1-smooth((distance-.45)/1.1))*coverage
rgba = np.stack([coverage, green, border, np.ones_like(coverage)], axis=-1)
mask_path = OUT/'T_VisualPolish_CampusMask.png'
Image.fromarray(np.uint8(np.clip(rgba,0,1)*255+.5), 'RGBA').save(mask_path)
config = {
    'version': 1, 'map': '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
    'asset_root': '/Game/GHSZcoolSmartFactory/VisualPolish',
    'atlas_bounds_uv_m': bounds, 'atlas_resolution': resolution,
    'cad_origin_uv_m': [239.33385,60.24019],
    'palette': {'campus':[.59,.665,.735], 'outer_green':[.435,.505,.445],
        'far_ground':[.58,.635,.69], 'boundary':[.23,.43,.66],
        'context_road':[.155,.208,.278], 'campus_road':[.335,.405,.475]},
    'boundary_opacity': .28,
    'far_fade_center_uv_m':[235.,100.], 'far_fade_start_m':420., 'far_fade_end_m':900.,
    'lighting': {'directional_intensity':3.65, 'directional_source_angle':9.0,
        'directional_color':[1.,.99,.975], 'skylight_intensity':.42,
        'skylight_color':[.92,.965,1.], 'ambient_occlusion_intensity':1.1,
        'ambient_occlusion_radius':150., 'ambient_occlusion_quality':80., 'bloom_intensity':.015},
    'mask': {'file':str(mask_path), 'sha256':hashlib.sha256(mask_path.read_bytes()).hexdigest(),
        'original_boundary_points':len(manifest['campus_boundary_uv_m']),
        'raster_boundary_points':len(points), 'max_boundary_error_m':polygon.hausdorff_distance(original),
        'channels':{'R':'campus coverage','G':'continuous outside greenery','B':'inside blue boundary','A':'opaque'}},
    'scope':'Material bindings and existing light/post-process values only. Original roof/dissolve, meshes, trees, parking, curbs, vehicles and all actor/component/instance transforms remain unchanged.'
}
(OUT/'visual_polish.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'mask':str(mask_path),'resolution':resolution,'boundary_error_m':config['mask']['max_boundary_error_m'],'sha256':config['mask']['sha256']}))
