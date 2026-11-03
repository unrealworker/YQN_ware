"""Reproduce manually reviewed orthogonal PV fields from the user plan.

The line-art cell grid is schematic. Broken ink cells are not roof holes.
Each polygon below is a reviewed continuous field boundary; main aisles, the
large C/E-shaped setbacks and the U-shaped opening remain explicitly empty.
"""
from pathlib import Path
import sys,json,hashlib,math
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from extract_mpr_road_outline import label_runs,signed_area
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/all-elements-outline-20261103.png'
OUT=ROOT/'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json'
DIAG=ROOT/'Saved/MPR/road_v5'
# Reviewed PV ink components. Device/roof-pipe components 3,4,8,9,20,22,
# 34 and the stepped external roof edge 71 are explicitly excluded.
COMPONENTS=[1,2,6,15,16,18,25,28,29,30,33,39,42,49,51,52]
# These coordinates are explicit orthogonal interpretation of the source,
# rather than pixel contour tracing. No closing/dilation is used, and no
# coordinate is inferred from the old perspective camera.
REVIEWED_FIELDS=[
 ([[778,401],[846,401],[846,410],[840,410],[840,417],[795,417],[795,410],[778,410]],'Two-row north array; retain broad lower-left/right setback, remove cell-edge teeth.'),
 ([[851,402],[923,402],[923,428],[851,428]],'Continuous rectangular grid; exclude north riser and regularize shallow top-cell gap.'),
 ([[928,407],[943,407],[943,451],[928,451]],'Continuous narrow rectangular north-east array.'),
 ([[828,422],[846,422],[846,472],[800,472],[800,463],[816,463],[816,452],[800,452],[800,430],[828,430]],'E-shaped field; retain large upper-left and middle-left white setbacks, fill line-grid breaks within arms.'),
 ([[778,433],[796,433],[796,471],[778,471]],'Continuous west vertical strip; remove cell-edge cracks.'),
 ([[851,442],[923,442],[923,462],[851,462]],'Continuous two-row field; former cross-shaped hole came from broken grid strokes, not a bounded clear roof opening.'),
 ([[930,454],[944,454],[944,462],[992,462],[992,474],[998,474],[998,482],[944,482],[944,486],[960,486],[960,494],[944,494],[944,500],[930,500]],'East branching field; retain large branch setbacks, fill former enclosed narrow slot and grid-cell breaks.'),
 ([[801,476],[846,476],[846,519],[801,519],[801,509],[830,509],[830,496],[801,496]],'Large C-shaped center field; preserve its clearly empty left opening, simplify small grid-cell protrusions.'),
 ([[778,476],[797,476],[797,519],[778,519]],'Continuous west vertical rectangular strip.'),
 ([[851,476],[925,476],[925,505],[851,505]],'Continuous multirow grid; former long narrow internal hole is broken cell-grid ink.'),
 ([[713,487],[768,487],[768,521],[751,521],[751,505],[728,505],[728,521],[713,521]],'Explicit U-shaped west array; preserve large open lower-center roof area; exclude top riser.'),
 ([[930,504],[944,504],[944,510],[950,510],[950,504],[981,504],[981,511],[966,511],[966,530],[944,530],[944,549],[930,549]],'East lower branching field; retain large exterior steps and the top branch gap, remove cell-size teeth.'),
 ([[851,509],[924,509],[924,518],[851,518]],'Single narrow continuous horizontal field.'),
 ([[851,522],[925,522],[925,571],[851,571]],'Continuous south-east array; regularize broken internal rows and shallow lower-edge cell crack.'),
 ([[778,523],[846,523],[846,571],[778,571]],'Continuous south-center array; former upper-left hole is connected white grid-cell interiors, not an equipment cutout.'),
 ([[674,529],[767,529],[767,571],[674,571]],'Continuous south-west array; exclude top riser, fill internal cell-grid void and shallow bottom teeth.'),
]
FIXTURE_COMPONENTS=[2,6,11,12,13,14,15,16,17,26,29,30,31,32,33,34,45,47,48,49,50,56,63,64,66,67,70,90,91,102]


def fixtures(gray):
 # Plan shell inset avoids dock tabs and the roof perimeter. Component IDs are
 # reviewed against source, not a newly invented evenly spaced fixture grid.
 mask=Image.new('L',(1728,910));d=ImageDraw.Draw(mask)
 d.polygon([(449,392),(984,392),(984,379),(1016,379),(1017,520),(994,520),
            (994,556),(972,556),(972,577),(947,577),(947,600),(476,600),(476,611),(449,611)],fill=255)
 labels=label_runs((gray<125)&(np.asarray(mask)>0));rows=[]
 for component in FIXTURE_COMPONENTS:
  y,x=np.nonzero(labels==component);assert 7<=len(x)<=100
  rows.append(dict(id=f'RoofFixture_{len(rows)+1:02}',source_component=component,
   center_px=[round(float(x.mean()),3),round(float(y.mean()),3)],
   bbox_px=[int(x.min()),int(y.min()),int(x.max()),int(y.max())],
   position_uncertainty_px=1.5,type='rooftop_vent_or_small_fixture',
   source_policy='Visible isolated rooftop symbol, visually reviewed; base center inferred from line-art silhouette, not survey'))
 return rows


def main():
 assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='d4741b2c6790b86e7b6c8f5365e135b44c17a1c3ccb420119ac3e5ad27ecddae','Source changed; reviewed component IDs require fresh visual inspection'
 im=Image.open(SOURCE).convert('RGB');g=np.asarray(im.convert('L'));regions=[]
 union_image=Image.new('1',im.size);ud=ImageDraw.Draw(union_image)
 for component,(outer,note) in zip(COMPONENTS,REVIEWED_FIELDS):
  assert all((a[0]==b[0]) != (a[1]==b[1]) for a,b in zip(outer,outer[1:]+outer[:1])),('Non-orthogonal or zero edge',component)
  x0=min(p[0]for p in outer);x1=max(p[0]for p in outer);y0=min(p[1]for p in outer);y1=max(p[1]for p in outer)
  region=dict(id=f'PVField_{len(regions)+1:02}',source_component=component,
   exterior_px=outer,holes_px=[],rings_px=[outer],bbox_px=[x0,y0,x1,y1],
   area_px2=round(abs(signed_area(outer)),3),manual_review_note=note,
   orthogonal_boundary=True,grid_cell_interiors_filled=True)
  regions.append(region);ud.polygon([tuple(p)for p in outer],fill=1)
 union=np.asarray(union_image,bool);holes_total=0
 # Source-defined empty aisle samples, not merely implementation assertions.
 samples={
  'west_vertical_pipe_not_panels':[774,500],
  'central_vertical_access':[848,500],
  'east_vertical_access':[927,500],
  'north_south_horizontal_access':[880,436],
  'middle_horizontal_access':[880,469],
  'south_horizontal_access':[880,520],
  'west_u_shaped_void':[741,512],
  'center_c_notch':[812,507],
  'far_south_clear_roof':[800,582],
  'left_device':[732,448],
 }
 checks=[]
 for name,(x,y) in samples.items():
  ok=not bool(union[y,x]);checks.append(dict(id=name,pixel=[x,y],clear=ok));assert ok,(name,x,y)
 result=dict(schema_version=1,status='review_ready_pixels_only',review_ready=True,
  source_image=SOURCE.relative_to(ROOT).as_posix(),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
  image_size=[1728,910],coordinate_frame='New user plan pixels, origin top-left. Register with mpr_plan_layout.plan_to_world; never the old camera.',
  method=dict(tracing='Manual review of all 16 source fields, explicit orthogonal polygon boundaries',
   morphology='NONE',review_version='orthogonal-fields-v2',
   cell_grid_policy='Fill schematic grid-cell interiors and broken-stroke false holes; source grid is not a module inventory',
   preserved_white_areas='Inter-field main aisles, large C/E-shaped setbacks, west U-shaped opening, major east branch setbacks',
   roof_equipment_excluded_components=[3,4,8,9,20,22,34,71],
   boundary_uncertainty_px=1.5),
  field_count=len(regions),interior_hole_count=holes_total,regions=regions,
  roof_fixtures=fixtures(g),roof_fixture_count=len(FIXTURE_COMPONENTS),
  validation=dict(clear_aisle_samples=checks,all_aisles_clear=True,no_random_fill=True,source_grid_not_module_inventory=True),
  limitations=['Grid cells are schematic artwork, not a physical panel count.','Manually interpreted orthogonal field edges imply about 1.5px boundary uncertainty.','Sampling should require a whole module to fit exterior minus holes to preserve aisles.'])
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 colored=np.zeros((*g.shape,4),dtype=np.uint8);colored[union]=[0,150,220,135]
 overlay=Image.alpha_composite(im.convert('RGBA'),Image.fromarray(colored));draw=ImageDraw.Draw(overlay)
 for reg in regions:
  ring=reg['exterior_px'];draw.line([tuple(v)for v in ring+[ring[0]]],fill=(0,105,235),width=1)
  for hole in reg['holes_px']:draw.line([tuple(v)for v in hole+[hole[0]]],fill=(235,110,0),width=1)
  x,y=reg['bbox_px'][:2];draw.text((x,y-7),reg['id'],fill=(0,30,160))
 for row in result['roof_fixtures']:
  x,y=row['center_px'];draw.ellipse((x-4,y-4,x+4,y+4),outline=(240,65,30),width=1)
 overlay.convert('RGB').save(DIAG/'solar_plan_target_overlay.png')
 overlay.crop((660,390,1020,585)).resize((1440,780)).convert('RGB').save(DIAG/'solar_plan_target_close.png')
 print(json.dumps(dict(status=result['status'],fields=len(regions),holes=holes_total,roof_fixtures=len(result['roof_fixtures']),pixel_area=int(union.sum()),validation=result['validation'])))


if __name__=='__main__':main()
