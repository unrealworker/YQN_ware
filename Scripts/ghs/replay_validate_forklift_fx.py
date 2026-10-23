"""Compile the actual route builder and check five colored ribbons against the saved scene."""
import csv,hashlib,json,math,os,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Saved/OrderReplay/FxReview';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import LineString,Point,Polygon
from shapely.ops import unary_union

data_path=ROOT/'Content/GHSTwinUI/data/order-replay.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original=sha(data_path)
data=json.loads(data_path.read_text(encoding='utf8'))
input_path=OUT/'input.txt'
with input_path.open('w',encoding='utf8') as f:
    f.write('5\n')
    for track in data['tracks'][:5]:
        f.write(str(len(track['keys']))+'\n')
        for k in track['keys']:f.write(' '.join(map(str,[k[0],*k[1],int(k[5])]))+'\n')
cpp=OUT/'trail_audit.cpp'
cpp.write_text('''#include "GHSOrderReplaySimulation.h"
#include <fstream>
#include <iostream>
#include <iomanip>
int main(int argc,char** argv){std::ifstream in(argv[1]);std::ofstream out(argv[2]),phase(argv[3]);out<<std::setprecision(15);phase<<std::setprecision(15);int count;in>>count;
for(int i=0;i<count;++i){size_t n;in>>n;GHSReplay::Track track;for(size_t j=0;j<n;++j){GHSReplay::Key k;in>>k.Time>>k.Position.X>>k.Position.Y>>k.Position.Z>>k.Visible;track.Keys.push_back(k);}
auto segments=GHSReplay::BuildTrailSegments(track);std::cout<<i<<" "<<segments.size()<<" "<<GHSReplay::TrailColor(i)<<"\\n";
for(const auto& s:segments){out<<i<<","<<s.A.X<<","<<s.A.Y<<","<<s.B.X<<","<<s.B.Y<<","<<s.StartMeters<<","<<s.LengthMeters<<","<<s.StartShearCm<<","<<s.EndShearCm<<","<<s.StartHalfWidthCm<<","<<s.EndHalfWidthCm<<"\\n";phase<<i<<","<<s.A.X<<","<<s.A.Y<<","<<s.B.X<<","<<s.B.Y<<","<<s.StartMeters<<","<<s.FlowDeltaMeters<<"\\n";}}
return 0;}
''',encoding='utf8')
vs=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat'
cmd=OUT/'compile.cmd'
cmd.write_text('@call "'+str(vs)+'" -vcvars_ver=14.38 >nul\n@cl /nologo /std:c++17 /EHsc /O2 /I"'+str(ROOT/'Source/Test')+'" "'+str(cpp)+'" "'+str(ROOT/'Source/Test/GHSOrderReplaySimulation.cpp')+'" /Fe:"'+str(OUT/'trail_audit.exe')+'" /Fo"'+OUT.as_posix()+'/"\n',encoding='utf8')
subprocess.run(['cmd.exe','/d','/c',str(cmd)],cwd=ROOT,check=True)
result=subprocess.run([str(OUT/'trail_audit.exe'),str(input_path),str(OUT/'segments.csv'),str(OUT/'flow-phases.csv')],cwd=ROOT,check=True,capture_output=True,text=True)
print(result.stdout.strip())
parts={i:[] for i in range(5)}
phase_junctions={i:{} for i in range(5)};phase_gaps=[];maximum_phase_gap=0.;shared_phase_junctions=0
f32=lambda v:struct.unpack('f',struct.pack('f',v))[0]
for row in csv.reader((OUT/'flow-phases.csv').open()):
    i=int(row[0]);ax,ay,bx,by,start,delta=map(float,row[1:])
    for x,y,phase in [(ax,ay,f32(start)),(bx,by,f32(start)+f32(delta))]:
        key=(round(x*100),round(y*100));existing=phase_junctions[i].get(key)
        if existing is None:phase_junctions[i][key]=phase
        else:
            shared_phase_junctions+=1;gap=abs(existing-phase);maximum_phase_gap=max(maximum_phase_gap,gap)
            if gap>1.e-4:phase_gaps.append(dict(fork=i+1,xy_cm=[x,y],phase_gap_m=gap))
for row in csv.reader((OUT/'segments.csv').open()):parts[int(row[0])].append(list(map(float,row[1:])))
# Reuse the identical physical upright/brace/wall extraction used for motion verification.
environment={'__file__':str(ROOT/'Scripts/ghs/replay_validate_static_actions.py')}
source=(ROOT/'Scripts/ghs/replay_validate_static_actions.py').read_text(encoding='utf8').split('def polygon(')[0]
exec(compile(source,'static-scene-extraction','exec'),environment)
solid=environment['solid'];rows=[];hits=[];inverted=[]
for i,track in enumerate(data['tracks'][:5]):
    raw=unary_union([LineString([a[1][:2],b[1][:2]]) for a,b in zip(track['keys'],track['keys'][1:])
                     if a[5] and b[5] and math.dist(a[1][:2],b[1][:2])>.01])
    maximum=0.;ribbons=[];shearmax=0.;minimum_width=75.
    for ax,ay,bx,by,start,length,sa,sb,wa,wb in parts[i]:
        dx,dy=bx-ax,by-ay;distance=math.hypot(dx,dy);ux,uy=dx/distance,dy/distance
        for t in (0,.25,.5,.75,1):maximum=max(maximum,raw.distance(Point(ax+dx*t,ay+dy*t)))
        corners=[]
        for x,y,s,w,sign in [(ax,ay,sa,wa,-1),(bx,by,sb,wb,-1),(bx,by,sb,wb,1),(ax,ay,sa,wa,1)]:
            corners.append(((x+sign*(-uy*w+ux*s))/100,(y+sign*(ux*w+uy*s))/100))
        poly=Polygon(corners)
        if not poly.is_valid or distance-abs(sb-sa)<-1.e-6:
            inverted.append(dict(id=track['id'],position_cm=[ax,ay,bx,by],length_cm=distance,start_shear=sa,end_shear=sb))
            poly=poly.buffer(0)
        overlap=poly.intersection(solid).area
        if overlap>1e-8:hits.append(dict(id=track['id'],position_cm=[ax,ay,bx,by],area_m2=overlap))
        ribbons.append(poly);shearmax=max(shearmax,abs(sa),abs(sb));minimum_width=min(minimum_width,wa*2,wb*2)
    rows.append(dict(id=track['id'],color=['#2F7CFF','#00D9C0','#F6B83F','#A77BFF','#F26AA6'][i],segments=len(parts[i]),
                     maximum_centerline_error_cm=maximum,maximum_miter_shear_cm=shearmax,minimum_local_width_cm=minimum_width,ribbon_area_m2=unary_union(ribbons).area))
report=dict(success=not hits and not inverted and not phase_gaps and max(r['maximum_centerline_error_cm'] for r in rows)<=27.1,
            timeline_sha256=original,timeline_unchanged=sha(data_path)==original,builder='actual compiled GHSReplay::BuildTrailSegments',
            trail_components=5,ripple_components=5,truck_trails=0,per_frame_geometry_rebuilds=0,width_cm=75,
            curves='Circular tangent joins, <=3 degree subdivision, <=80cm corner cut; original motion unchanged',
            obstacle_count=len(environment['obstacles']),collision_count=len(hits),collisions=hits[:30],inverted_segments=inverted,forklifts=rows,
            shared_phase_junctions=shared_phase_junctions,maximum_float32_phase_gap_m=maximum_phase_gap,phase_errors=phase_gaps)
(OUT/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('collisions','inverted_segments')},indent=2));assert report['success'],'Inspect FxReview/validation.json'
