"""Review final MPR metadata against the latest plan without launching DCCs.

This is a registered XY layout audit, not proof of render-camera or 3D visual
fidelity. Run after site/context/architecture manifests have all been rebuilt.
"""
from pathlib import Path
import argparse,hashlib,json,math
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from mpr_plan_layout import load_registration,world_to_plan

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'SourceAssets/MPR/reference_v4'
SOURCE=BASE/'references/all-elements-outline-20261103.png'
OUT=BASE/'validation'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    if not values:return dict(count=0)
    a=np.asarray(values,float)
    return dict(count=len(values),median_px=float(np.median(a)),p95_px=float(np.percentile(a,95)),max_px=float(a.max()))


def point_segment_distance(points,poly):
    p=np.asarray(points,float);q=np.asarray(poly,float);a=q;b=np.roll(q,-1,axis=0)
    v=b-a;d=np.maximum((v*v).sum(axis=1),1e-12)
    t=np.clip(((p[:,None,:]-a[None,:,:])*v[None,:,:]).sum(axis=2)/d[None,:],0,1)
    return np.linalg.norm(p[:,None,:]-(a[None,:,:]+t[:,:,None]*v[None,:,:]),axis=2).min(axis=1)


def polygon(draw,points,color,width=1):
    if len(points)>2:draw.line([tuple(p)for p in points+[points[0]]],fill=color,width=width)


def actual_instance_polygon(item,bounds):
    scale=item.get('scale',[1,1,1]);yaw=math.radians(item.get('rotation_deg',0));c,s=math.cos(yaw),math.sin(yaw)
    x0,x1=[v*scale[0]for v in bounds[0]];y0,y1=[v*scale[1]for v in bounds[1]]
    px,py=item['position_m'][:2]
    return [[px+x*c-y*s,py+x*s+y*c]for x,y in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]


def main():
    paths=dict(registration=BASE/'site/plan_registration_v5.json',
        context=BASE/'context/reference_context_ground_layout.json',
        context_manifest=BASE/'context/manifest.json',site=BASE/'site/manifest.json',
        roads=BASE/'site/road_outline_v5.json',railway=BASE/'site/plan_railway_v5.json',vegetation=BASE/'site/plan_vegetation_v5.json',
        solar=BASE/'architecture/plan_solar_v5.json',architecture=BASE/'architecture/reference_shell_manifest.json',
        props=BASE/'props/manifest.json')
    data={k:read(v)for k,v in paths.items()};reg=data['registration'];site=data['site'];arch=data['architecture']
    current_checks=dict(
        context_registration=data['context'].get('plan_registration_sha256')==sha(paths['registration']),
        site_registration=site.get('plan_registration')==reg,
        site_road_source=site.get('road_boundary_source_sha256')==data['roads']['source_sha256'],
        site_railway_source=site.get('railway_layout')==data['railway'],
        site_vegetation_source=site.get('planting',{}).get('source_sha256')==data['vegetation']['source_sha256'],
        architecture_solar=arch.get('roof_layout',{}).get('source_sha256')==sha(paths['solar']),
        architecture_registration=arch.get('roof_layout',{}).get('plan_registration')==reg)
    if not all(current_checks.values()):
        raise RuntimeError('Refusing to archive stale mixed-generation inputs: '+json.dumps(current_checks))
    OUT.mkdir(parents=True,exist_ok=True)
    im=Image.open(SOURCE).convert('RGBA');overlay=Image.new('RGBA',im.size);draw=ImageDraw.Draw(overlay)
    # Road boundary geometry is authoritative source input. This does not
    # inspect triangles inside exported road FBX meshes.
    for row in data['roads']['polygons_px']:
        polygon(draw,row['exterior'],(10,120,225,210),2)
        for hole in row.get('holes',[]):polygon(draw,hole,(10,120,225,210),2)
    railway_rows=[]
    for row in site['railway_layout']['tracks']:
        draw.line([tuple(p)for p in row['path_px']],fill=(118,76,30,220),width=1)
        railway_rows.append(dict(id=row['id'],path_px=row['path_px'],source='site railway_layout input trace',
            confidence=row.get('confidence'),position_uncertainty_px=row.get('position_uncertainty_px')))
    for side,path in site['railway_layout'].get('ballast_edges_px',{}).items():
        draw.line([tuple(p)for p in path],fill=(118,76,30,140),width=1)
    building_rows=[]
    for row in data['context']['buildings']:
        if 'footprint_m' not in row:continue
        px=world_to_plan(row['footprint_m'],reg);polygon(draw,px,(190,70,205,220),2)
        original=row.get('physical_frame',{}).get('source_footprint_m')
        audit=dict(id=row['id'],type=row['type'],projected_footprint_px=px)
        if original:
            target=world_to_plan(original,reg)
            distances=np.r_[point_segment_distance(px,target),point_segment_distance(target,px)]
            audit.update(boundary_displacement_px_max=float(distances.max()),boundary_displacement_px_rms=float(np.sqrt(np.mean(distances**2))))
        building_rows.append(audit)
    polygon(draw,world_to_plan(arch['footprint_outline_m'],reg),(116,38,180,255),2)
    tree_errors=[];tree_rows=[]
    sx,sy=reg['scale_m_per_px']
    for row in site['planting']['tree_positions']:
        x,y=world_to_plan(row['position_m'],reg);r=row['crown_radius_m'];rx=r/abs(sx);ry=r/abs(sy)
        draw.ellipse((x-rx,y-ry,x+rx,y+ry),outline=(30,155,60,170),width=1)
        draw.line((x-1.5,y,x+1.5,y),fill=(0,110,25,220),width=1)
        target=row.get('reference_pixel');err=math.dist([x,y],target)if target else None
        if err is not None:tree_errors.append(err)
        tree_rows.append(dict(id=row.get('source_id'),projected_center_px=[x,y],reference_pixel=target,center_error_px=err))
    bounds={r['name']:r['bounds_m']for r in data['props']['meshes']}
    trailer_rows=[];trailer_errors=[];railcar_rows=[];railcar_errors=[]
    for name,instances in site.get('instances',{}).items():
        is_railcar='FreightBoxcar'in name
        if 'Trailer' not in name and not is_railcar:continue
        for i,row in enumerate(instances):
            points=world_to_plan(actual_instance_polygon(row,bounds[name]),reg)
            color=(135,90,20,230)if is_railcar else(235,110,10,220)
            polygon(draw,points,color,1)
            actual=world_to_plan(row['position_m'],reg);target=row.get('reference_pixel')
            error=math.dist(actual,target)if target else None
            if target:
                draw.line([tuple(target),tuple(actual)],fill=color,width=1)
                (railcar_errors if is_railcar else trailer_errors).append(error)
            (railcar_rows if is_railcar else trailer_rows).append(dict(mesh=name,instance_index=i,reference_row=row.get('reference_row'),plan_track_id=row.get('plan_track_id'),
                projected_center_px=actual,reference_pixel=target,center_error_px=error,
                cad_dock_index=row.get('cad_dock_index'),stand_shift_m=row.get('stand_shift_m'),projected_outline_px=points))
    target_mask=Image.new('1',im.size);td=ImageDraw.Draw(target_mask)
    for row in data['solar']['regions']:
        td.polygon([tuple(p)for p in row['exterior_px']],fill=1)
        polygon(draw,row['exterior_px'],(20,105,250,170),1)
        for hole in row['holes_px']:
            td.polygon([tuple(p)for p in hole],fill=0);polygon(draw,hole,(255,120,20,180),1)
    current_mask=Image.new('1',im.size);cd=ImageDraw.Draw(current_mask)
    for row in arch['roof_layout']['strips']:
        x,w,y0,y1=row['x'],row['width'],row['y0'],row['y1']
        px=world_to_plan([[x-w/2,y0],[x+w/2,y0],[x+w/2,y1],[x-w/2,y1]],reg)
        cd.polygon([tuple(p)for p in px],fill=1);draw.polygon([tuple(p)for p in px],fill=(20,130,235,150))
    a=np.asarray(current_mask,bool);b=np.asarray(target_mask,bool)
    fixture_rows=[];fixture_errors=[]
    targets=data['solar'].get('roof_fixtures',[])
    seen_fixture_targets=set()
    for name,instances in arch.get('instances',{}).items():
        if name not in ('SM_MPR4_RoofHVAC','SM_MPR4_RoofLight'):continue
        for i,row in enumerate(instances):
            actual=world_to_plan(row['position_m'],reg);x,y=actual;target=row.get('source_pixel')
            if target is None:raise AssertionError('Roof fixture lacks source_pixel; refusing index-based matching')
            matching=[t for t in targets if math.dist(t['center_px'],target)<1e-4]
            assert len(matching)==1,('Unmatched or duplicate fixture source',target)
            source_id=matching[0]['id'];assert source_id not in seen_fixture_targets,source_id;seen_fixture_targets.add(source_id)
            draw.ellipse((x-3,y-3,x+3,y+3),outline=(230,50,35,230),width=1)
            error=math.dist(actual,target);fixture_errors.append(error)
            fixture_rows.append(dict(mesh=name,instance_index=i,source_id=source_id,center_px=actual,reference_pixel=target,center_error_px=error))
    combined=Image.alpha_composite(im,overlay).convert('RGB');d=ImageDraw.Draw(combined)
    try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    except OSError:font=ImageFont.load_default()
    d.rectangle((0,0,1728,51),fill='white')
    d.text((12,4),'REGISTERED XY PLAN REVIEW  |  Blue roads/PV  Magenta buildings  Green trees  Orange trailers  Brown rail  Red fixtures',fill='#173c58',font=font)
    d.text((12,27),'Layout metadata only: non-uniform plan scales and orthogonal 3D buildings cause expected outline differences; not render fidelity.',fill='#584c39',font=font)
    combined.save(OUT/'plan_alignment.png')
    result=dict(schema_version=1,status='metadata_plan_alignment_review',all_inputs_current=True,
        source_image=SOURCE.relative_to(ROOT).as_posix(),source_sha256=sha(SOURCE),
        output_image=dict(path=(OUT/'plan_alignment.png').relative_to(ROOT).as_posix(),sha256=sha(OUT/'plan_alignment.png')),
        inputs={k:dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))for k,p in paths.items()},
        freshness_checks=current_checks,coordinate_mapping='world_to_plan from independent XY registration; no perspective image inverse',
        counts=dict(context_buildings=len(building_rows),trees=len(tree_rows),trailers=len(trailer_rows),rail_tracks=len(railway_rows),railcars=len(railcar_rows),solar_strips=len(arch['roof_layout']['strips']),roof_fixtures=len(fixture_rows)),
        building_boundary_regularization=stats([r['boundary_displacement_px_max']for r in building_rows if 'boundary_displacement_px_max'in r]),
        tree_center_error=stats(tree_errors),trailer_reference_center_displacement=stats(trailer_errors),railcar_reference_center_displacement=stats(railcar_errors),fixture_center_error=stats(fixture_errors),
        solar_raster_diagnostic=dict(target_px=int(b.sum()),projected_modules_px=int(a.sum()),outside_target_px=int((a&~b).sum()),
            sampled_target_fraction=float((a&b).sum()/max(1,b.sum())),
            caution='One-pixel raster rounding and actual inter-module gaps affect these counts; use polygon/module fit validation for correctness'),
        trees_rejected=site['planting'].get('rejected',[]),trailer_layout_audit=site.get('trailer_layout_audit'),
        buildings=building_rows,trees=tree_rows,trailers=trailer_rows,railway_tracks=railway_rows,railcars=railcar_rows,roof_fixtures=fixture_rows,
        omitted_roof_fixture_sources=[r for r in targets if r['id']not in seen_fixture_targets],
        limitations=['Layout metadata and source road polygons are audited; this does not independently inspect imported Unreal or exported FBX triangle geometry.',
            'The plan has non-uniform X/Y scaling; physical orthogonal buildings and circular crowns project differently from schematic symbols.',
            'CAD dock locking and physical clearance can cause explicit trailer/tree deviations.',
            'A plan overlay is not pixel-perfect 3D fidelity or a performance measurement.'])
    (OUT/'plan_alignment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k]for k in ['status','counts','freshness_checks','tree_center_error','trailer_reference_center_displacement','fixture_center_error']}))


if __name__=='__main__':main()
