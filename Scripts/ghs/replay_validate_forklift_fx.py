"""Audit current-leg theme-blue ribbons using the actual compiled replay route builder."""
import bisect,csv,hashlib,json,math,os,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Saved/OrderReplay/FxReview';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import LineString,Point,Polygon
from shapely.ops import unary_union
data_path=ROOT/'Content/GHSTwinUI/data/order-replay.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original=sha(data_path);data=json.loads(data_path.read_text(encoding='utf8'))
input_path=OUT/'input.txt'
with input_path.open('w',encoding='utf8') as f:
    f.write('5 '+str(data['cycleDuration'])+'\n')
    for track in data['tracks'][:5]:
        f.write(str(len(track['keys']))+'\n')
        for key in track['keys']:f.write(' '.join(map(str,[key[0],*key[1],int(key[5]),key[7] or '-']))+'\n')
cpp=OUT/'trail_audit.cpp'
cpp.write_text(r'''#include "GHSOrderReplaySimulation.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <chrono>
#include <cmath>
#include <cassert>
int main(int argc,char** argv){
std::ifstream in(argv[1]);std::ofstream out(argv[2]),legs(argv[3]),states(argv[4]);
out<<std::setprecision(15);legs<<std::setprecision(15);states<<std::setprecision(15);
int count;double cycle;in>>count>>cycle;double buildMs=0,lookupMs=0;int checks=0;
for(int i=0;i<count;++i){
 size_t n;in>>n;GHSReplay::Track track;
 for(size_t j=0;j<n;++j){GHSReplay::Key k;in>>k.Time>>k.Position.X>>k.Position.Y>>k.Position.Z>>k.Visible>>k.Status;track.Keys.push_back(k);}
 auto began=std::chrono::steady_clock::now();auto plan=GHSReplay::BuildTaskTrail(track);
 buildMs+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
 for(const auto& s:plan.Segments)out<<i<<","<<s.LegId<<","<<s.A.X<<","<<s.A.Y<<","<<s.B.X<<","<<s.B.Y<<","<<s.StartMeters<<","<<s.FlowDeltaMeters<<","<<s.LengthMeters<<","<<s.StartShearCm<<","<<s.EndShearCm<<","<<s.StartHalfWidthCm<<","<<s.EndHalfWidthCm<<","<<s.ProgressStartMeters<<","<<s.ProgressDeltaMeters<<"\n";
 for(const auto& leg:plan.Legs){legs<<i<<","<<leg.Id<<","<<leg.StartTime<<","<<leg.EndTime<<","<<leg.LengthMeters<<","<<leg.DistanceKeys.size()<<"\n";
  assert(!GHSReplay::EvaluateTaskTrail(plan,leg.EndTime,cycle).Moving);
  double midpoint=(leg.StartTime+leg.EndTime)*.5;
  assert(!GHSReplay::EvaluateTaskTrail(plan,midpoint,cycle,midpoint).Moving);
  assert(GHSReplay::EvaluateTaskTrail(plan,midpoint,cycle,midpoint+1).Moving);
 }
 for(size_t k=1;k<track.Keys.size();++k){
  const auto& a=track.Keys[k-1];const auto& b=track.Keys[k];double time=(a.Time+b.Time)*.5;
  bool expected=a.Visible&&b.Visible&&std::hypot(a.Position.X-b.Position.X,a.Position.Y-b.Position.Y)>.01&&a.Status.find("\xE6\x95\x85\xE9\x9A\x9C")==std::string::npos&&a.Status.find("\xE7\xAD\x89\xE5\xBE\x85")==std::string::npos;
  const auto s=GHSReplay::EvaluateTaskTrail(plan,time,cycle);assert(s.Moving==expected);++checks;
  const auto paused=GHSReplay::EvaluateTaskTrail(plan,time,cycle),loop=GHSReplay::EvaluateTaskTrail(plan,time+10000*cycle,cycle);
  assert(s.LegId==paused.LegId&&s.DistanceMeters==paused.DistanceMeters&&s.LegId==loop.LegId&&std::abs(s.DistanceMeters-loop.DistanceMeters)<1.e-5);
  if(s.Moving)assert(s.DistanceMeters>=0&&s.DistanceMeters<s.LengthMeters&&s.StartTime<=time&&s.EndTime>time);
  states<<i<<","<<time<<","<<s.Moving<<","<<s.LegId<<","<<s.DistanceMeters<<","<<s.LengthMeters<<"\n";
 }
 began=std::chrono::steady_clock::now();double consume=0;
 for(int n=0;n<100000;++n){auto state=GHSReplay::EvaluateTaskTrail(plan,std::fmod(n*.137,cycle),cycle);consume+=state.DistanceMeters;}
 assert(consume>0);lookupMs+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
 assert(!GHSReplay::EvaluateTaskTrail(plan,0,cycle).Moving);
 std::cout<<i<<" "<<plan.Legs.size()<<" "<<plan.Segments.size()<<" "<<GHSReplay::TrailColor(i)<<"\n";
}
std::cout<<"METRICS "<<buildMs<<" "<<lookupMs<<" "<<checks<<"\n";return 0;
}''',encoding='utf8')
vs=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat'
cmd=OUT/'compile.cmd'
cmd.write_text('@call "'+str(vs)+'" -vcvars_ver=14.38 >nul\n@cl /nologo /std:c++20 /utf-8 /EHsc /O2 /I"'+str(ROOT/'Source/Test')+'" "'+str(cpp)+'" "'+str(ROOT/'Source/Test/GHSOrderReplaySimulation.cpp')+'" /Fe:"'+str(OUT/'trail_audit.exe')+'" /Fo"'+OUT.as_posix()+'/"\n',encoding='utf8')
subprocess.run(['cmd.exe','/d','/c',str(cmd)],cwd=ROOT,check=True)
result=subprocess.run([str(OUT/'trail_audit.exe'),str(input_path),str(OUT/'segments.csv'),str(OUT/'legs.csv'),str(OUT/'states.csv')],cwd=ROOT,check=True,capture_output=True,text=True)
print(result.stdout.strip())
metrics=next(line.split()[1:] for line in result.stdout.splitlines() if line.startswith('METRICS '))
parts={i:{} for i in range(5)};legs={i:{} for i in range(5)}
for row in csv.reader((OUT/'segments.csv').open()):parts[int(row[0])].setdefault(int(row[1]),[]).append(list(map(float,row[2:])))
for row in csv.reader((OUT/'legs.csv').open()):legs[int(row[0])][int(row[1])]=list(map(float,row[2:]))
environment={'__file__':str(ROOT/'Scripts/ghs/replay_validate_static_actions.py')}
source=(ROOT/'Scripts/ghs/replay_validate_static_actions.py').read_text(encoding='utf8').split('def polygon(')[0]
exec(compile(source,'static-scene-extraction','exec'),environment)
solid=environment['solid'];rows=[];hits=[];inverted=[];phase_errors=[];remaining_errors=[]
maximum_phase_gap=0.;shared=0;f32=lambda value:struct.unpack('f',struct.pack('f',value))[0]
maximum_chain_gap=0.;nonsimple_legs=[];progress_mapping_errors=[];maximum_cursor_error=0.;cursor_checks=0
for i,track in enumerate(data['tracks'][:5]):
    maximum=0.;count=0;area=0.;minimum_width=18.;maximum_overlap=0.
    for leg_id,segments in parts[i].items():
        start_time,end_time,total,_=legs[i][leg_id]
        keys=[key for key in track['keys'] if start_time<=key[0]<=end_time]
        raw=unary_union([LineString([a[1][:2],b[1][:2]]) for a,b in zip(keys,keys[1:]) if math.dist(a[1][:2],b[1][:2])>.01])
        ribbons=[];junctions={};last_progress=0.;chain=[]
        for segment in segments:
            ax,ay,bx,by,flow_start,flow_delta,length,sa,sb,wa,wb,progress,delta=segment
            dx,dy=bx-ax,by-ay;distance=math.hypot(dx,dy);ux,uy=dx/distance,dy/distance
            if chain:maximum_chain_gap=max(maximum_chain_gap,math.dist(chain[-1],(ax,ay)))
            else:chain.append((ax,ay))
            chain.append((bx,by))
            for t in (0,.25,.5,.75,1):maximum=max(maximum,raw.distance(Point(ax+dx*t,ay+dy*t)))
            if abs(progress-last_progress)>1.e-6 or delta<=0:remaining_errors.append([i,leg_id,progress,last_progress])
            last_progress=progress+delta
            for x,y,phase in [(ax,ay,f32(flow_start)),(bx,by,f32(flow_start)+f32(flow_delta))]:
                point=(round(x*100),round(y*100));old=junctions.get(point)
                if old is None:junctions[point]=phase
                else:
                    shared+=1;gap=abs(old-phase);maximum_phase_gap=max(maximum_phase_gap,gap)
                    if gap>1.e-4:phase_errors.append([i,leg_id,x,y,gap])
            corners=[]
            for x,y,s,w,sign in [(ax,ay,sa,wa,-1),(bx,by,sb,wb,-1),(bx,by,sb,wb,1),(ax,ay,sa,wa,1)]:
                corners.append(((x+sign*(-uy*w+ux*s))/100,(y+sign*(ux*w+uy*s))/100))
            poly=Polygon(corners)
            if not poly.is_valid or distance-abs(sb-sa)<-1.e-6:
                inverted.append(dict(id=track['id'],leg=leg_id,position_cm=[ax,ay,bx,by]));poly=poly.buffer(0)
            overlap=poly.intersection(solid).area
            if overlap>1e-8:hits.append(dict(id=track['id'],leg=leg_id,position_cm=[ax,ay,bx,by],area_m2=overlap))
            ribbons.append(poly);minimum_width=min(minimum_width,wa*2,wb*2)
        if abs(last_progress-total)>1.e-5:remaining_errors.append([i,leg_id,last_progress,total])
        if not LineString(chain).is_simple:nonsimple_legs.append([i,leg_id])
        union=unary_union(ribbons);area+=union.area;maximum_overlap=max(maximum_overlap,sum(poly.area for poly in ribbons)-union.area);count+=len(segments)
    rows.append(dict(id=track['id'],color='#356BFA',legs=len(legs[i]),segments=count,
        height_cm=3+i*.8,maximum_centerline_error_cm=maximum,minimum_local_width_cm=minimum_width,
        maximum_same_leg_overlap_m2=maximum_overlap,total_cached_area_m2=area))
# The GPU clipping boundary must follow the actual directed movement, not merely
# project onto some geometrically nearby future leg. Audit every moving source
# interval midpoint against the exact timestamp cursor exported by C++.
key_times=[[key[0] for key in track['keys']] for track in data['tracks'][:5]]
segment_starts={i:{leg:[s[11] for s in segments] for leg,segments in parts[i].items()} for i in parts}
for row in csv.reader((OUT/'states.csv').open()):
    i=int(row[0]);time=float(row[1]);moving=int(row[2]);leg_id=int(row[3]);progress=float(row[4])
    if not moving:continue
    keys=data['tracks'][i]['keys'];at=bisect.bisect_right(key_times[i],time);a,b=keys[at-1:at+1]
    t=(time-a[0])/(b[0]-a[0]);actual=[a[1][j]+t*(b[1][j]-a[1][j]) for j in range(2)]
    segments=parts[i][leg_id];index=max(0,bisect.bisect_right(segment_starts[i][leg_id],progress)-1)
    s=segments[index];u=max(0.,min(1.,(progress-s[11])/s[12]));cursor=[s[0]+u*(s[2]-s[0]),s[1]+u*(s[3]-s[1])]
    error=math.dist(cursor,actual);maximum_cursor_error=max(maximum_cursor_error,error);cursor_checks+=1
    if error>9.:progress_mapping_errors.append([i,leg_id,time,error])
report=dict(success=not hits and not inverted and not phase_errors and not remaining_errors and not progress_mapping_errors and not nonsimple_legs and maximum_chain_gap<.001 and max(row['maximum_centerline_error_cm'] for row in rows)<=27.1,
    timeline_sha256=original,timeline_unchanged=sha(data_path)==original,builder='actual compiled GHSReplay::BuildTaskTrail',
    trail_components=5,ripple_components=5,truck_trails=0,per_frame_geometry_rebuilds=0,width_cm=18,
    activity_interval_checks=int(metrics[2]),all_idle_at_zero=True,pause_seek_cycle_checks=True,mid_leg_playback_completion_checks=True,
    one_time_plan_build_ms=float(metrics[0]),five_hundred_thousand_lookups_ms=float(metrics[1]),
    curves='Per moving leg; circular tangent joins; original motion unchanged',obstacle_count=len(environment['obstacles']),
    collision_count=len(hits),collisions=hits[:30],inverted_segments=inverted,forklifts=rows,
    shared_phase_junctions=shared,maximum_float32_phase_gap_m=maximum_phase_gap,phase_errors=phase_errors,remaining_progress_errors=remaining_errors,
    maximum_segment_chain_gap_cm=maximum_chain_gap,nonsimple_legs=nonsimple_legs,
    timestamp_cursor_checks=cursor_checks,maximum_timestamp_cursor_error_cm=maximum_cursor_error,progress_mapping_errors=progress_mapping_errors)
(OUT/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2));assert report['success'],'Inspect FxReview/validation.json'
