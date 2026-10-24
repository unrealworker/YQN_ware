#include "GHSOrderReplaySimulation.h"
#include <algorithm>
#include <cmath>
#include <set>
#include <map>
#include <functional>
#include <queue>
#include <limits>

namespace GHSReplay
{
static double Lerp(double A,double B,double T){return A+(B-A)*T;}
static double Angle(double A,double B,double T){return A+std::remainder(B-A,360.)*T;}
const char* TrailColor(int DeviceIndex)
{
    return DeviceIndex>=0&&DeviceIndex<ForkCount?"#356BFA":"";
}
std::vector<TrailSegment> BuildTrailSegments(const Track& Track)
{
    std::vector<TrailSegment> Result;std::vector<Vec> Run;
    using LineKey=std::array<long long,2>;
    std::map<LineKey,std::vector<std::pair<double,double>>> Covered;
    double DistanceMeters=0;
    auto Length=[](const Vec& A,const Vec& B){return std::hypot(B.X-A.X,B.Y-A.Y);};
    auto Flush=[&]()
    {
        if(Run.size()<2){Run.clear();return;}
        std::vector<bool> Keep(Run.size(),false);Keep.front()=Keep.back()=true;
        std::function<void(size_t,size_t)> Simplify=[&](size_t A,size_t B)
        {
            if(B<=A+1)return;double Maximum=2.;size_t Split=B;
            const auto& P=Run[A];const auto& Q=Run[B];const double DX=Q.X-P.X,DY=Q.Y-P.Y,L2=DX*DX+DY*DY;
            for(size_t I=A+1;I<B;++I)
            {
                const double T=L2>1.e-8?std::clamp(((Run[I].X-P.X)*DX+(Run[I].Y-P.Y)*DY)/L2,0.,1.):0;
                const double D=std::hypot(Run[I].X-P.X-T*DX,Run[I].Y-P.Y-T*DY);
                if(D>Maximum){Maximum=D;Split=I;}
            }
            if(Split<B){Keep[Split]=true;Simplify(A,Split);Simplify(Split,B);}
        };
        Simplify(0,Run.size()-1);
        std::vector<Vec> Points,Curve;std::vector<double> HalfWidths;
        for(size_t I=0;I<Run.size();++I)if(Keep[I])Points.push_back(Run[I]);
        auto Append=[&](const Vec& P,double Width=TrailWidthCm*.5)
        {
            if(Curve.empty()||Length(Curve.back(),P)>.001){Curve.push_back(P);HalfWidths.push_back(Width);}
            else HalfWidths.back()=std::min(HalfWidths.back(),Width);
        };
        Append(Points.front());
        for(size_t I=1;I+1<Points.size();++I)
        {
            const auto &A=Points[I-1],&B=Points[I],&C=Points[I+1];
            const double LA=Length(A,B),LB=Length(B,C);
            const Vec U{(B.X-A.X)/LA,(B.Y-A.Y)/LA,0},V{(C.X-B.X)/LB,(C.Y-B.Y)/LB,0};
            const double Cos=std::clamp(U.X*V.X+U.Y*V.Y,-1.,1.);
            // A reversal retraces the same path: never invent a bulb outside the aisle.
            if(Cos>.999999||Cos<-.8660254){Append(B);continue;}
            const double Cut=std::min({TrailCornerCutCm,.45*LA,.45*LB});
            const Vec P{B.X-U.X*Cut,B.Y-U.Y*Cut,B.Z},Q{B.X+V.X*Cut,B.Y+V.Y*Cut,B.Z};
            const int Steps=std::max(4,int(std::ceil(std::acos(Cos)/(3.*3.14159265358979323846/180.))));
            const double Cross=U.X*V.Y-U.Y*V.X,Sign=Cross<0?-1.:1.;
            const double Radius=Cut*std::sqrt((1.+Cos)/(1.-Cos));
            // The rare short pickup approach has a smaller radius than the usual
            // ribbon half-width. Taper locally; never fold its inside edge backwards.
            const double HalfWidth=std::min(TrailWidthCm*.5,Radius*.8);
            Append(P,HalfWidth);
            const Vec Center{P.X-U.Y*Radius*Sign,P.Y+U.X*Radius*Sign,B.Z};
            const double StartAngle=std::atan2(P.Y-Center.Y,P.X-Center.X);
            // Actual circular fillets give a constant turn radius. The movement keys
            // themselves stay untouched; only this floor ribbon is rounded.
            for(int J=1;J<=Steps;++J)
            {
                const double Angle=StartAngle+Sign*std::acos(Cos)*double(J)/Steps;
                Append(J==Steps?Q:Vec{Center.X+Radius*std::cos(Angle),Center.Y+Radius*std::sin(Angle),B.Z},HalfWidth);
            }
        }
        Append(Points.back());
        auto Turn=[](const Vec& A,const Vec& B,const Vec& C)
        {
            const double LX=std::hypot(B.X-A.X,B.Y-A.Y),LY=std::hypot(C.X-B.X,C.Y-B.Y);
            const double Cos=((B.X-A.X)*(C.X-B.X)+(B.Y-A.Y)*(C.Y-B.Y))/(LX*LY);
            if(Cos<-.8660254)return 0.;
            return ((B.X-A.X)*(C.Y-B.Y)-(B.Y-A.Y)*(C.X-B.X))/(LX*LY*(1.+Cos));
        };
        for(size_t I=1;I<Curve.size();++I)
        {
            const Vec A=Curve[I-1],B=Curve[I];const double L=Length(A,B);if(L<.01)continue;
            const double StartShear=I>1?Turn(Curve[I-2],A,B)*HalfWidths[I-1]:0.;
            const double EndShear=I+1<Curve.size()?-Turn(A,B,Curve[I+1])*HalfWidths[I]:0.;
            double R=std::atan2(B.Y-A.Y,B.X-A.X);if(R<0)R+=3.14159265358979323846;if(R>=3.14159265358979323846)R-=3.14159265358979323846;
            const long long AngleKey=std::llround(R*1.e6);R=double(AngleKey)/1.e6;
            const double C=std::cos(R),S=std::sin(R),PA=A.X*C+A.Y*S,PB=B.X*C+B.Y*S;
            const LineKey K{AngleKey,std::llround((-A.X*S+A.Y*C)*2.)};
            auto& Intervals=Covered[K];const double Low=std::min(PA,PB),High=std::max(PA,PB);
            std::vector<std::pair<double,double>> Fresh;double Cursor=Low;
            for(const auto& Span:Intervals)
            {
                if(Span.second<=Cursor)continue;if(Span.first>=High)break;
                if(Span.first>Cursor+.01)Fresh.emplace_back(Cursor,std::min(Span.first,High));
                Cursor=std::max(Cursor,Span.second);if(Cursor>=High)break;
            }
            if(Cursor<High-.01)Fresh.emplace_back(Cursor,High);
            for(const auto& Span:Fresh)
            {
                double U=(Span.first-PA)/(PB-PA),V=(Span.second-PA)/(PB-PA);if(U>V)std::swap(U,V);
                auto At=[&](double T){return Vec{Lerp(A.X,B.X,T),Lerp(A.Y,B.Y,T),Lerp(A.Z,B.Z,T)};};
                Result.push_back({At(U),At(V),DistanceMeters+U*L/100.,(V-U)*L/100.,
                    Lerp(StartShear,EndShear,U),Lerp(StartShear,EndShear,V),
                    Lerp(HalfWidths[I-1],HalfWidths[I],U),Lerp(HalfWidths[I-1],HalfWidths[I],V)});
            }
            Intervals.emplace_back(Low,High);std::sort(Intervals.begin(),Intervals.end());
            std::vector<std::pair<double,double>> Merged;
            for(const auto& Span:Intervals)
            {if(Merged.empty()||Span.first>Merged.back().second+.01)Merged.push_back(Span);else Merged.back().second=std::max(Merged.back().second,Span.second);}
            Intervals=std::move(Merged);DistanceMeters+=L/100.;
        }
        Run.clear();
    };
    for(size_t I=1;I<Track.Keys.size();++I)
    {
        const auto& A=Track.Keys[I-1];const auto& B=Track.Keys[I];
        if(!A.Visible||!B.Visible){Flush();continue;}
        if(Length(A.Position,B.Position)<.01)continue;
        if(Run.empty())Run.push_back(A.Position);Run.push_back(B.Position);
    }
    Flush();
    // A retraced branch can be retained from a later trip after geometric deduplication.
    // Trip mileage is not a valid UV coordinate there: identical physical junctions
    // would jump to unrelated light phases. Build one shared distance field once.
    using PointKey=std::array<long long,2>;
    std::map<PointKey,std::vector<size_t>> NodeIds;
    std::vector<Vec> NodePositions;
    std::vector<std::vector<std::pair<size_t,double>>> Edges;
    auto Node=[&](const Vec& P)
    {
        const PointKey K{std::llround(P.X*2.),std::llround(P.Y*2.)};
        for(long long X=K[0]-1;X<=K[0]+1;++X)for(long long Y=K[1]-1;Y<=K[1]+1;++Y)
        {
            auto It=NodeIds.find({X,Y});if(It==NodeIds.end())continue;
            for(size_t Id:It->second)if(Length(P,NodePositions[Id])<=.51)return Id;
        }
        const size_t Id=Edges.size();NodeIds[K].push_back(Id);NodePositions.push_back(P);Edges.emplace_back();return Id;
    };
    std::vector<std::pair<size_t,size_t>> OriginalNodes,SegmentNodes;
    for(const auto& S:Result)
    {
        const size_t A=Node(S.A),B=Node(S.B);OriginalNodes.emplace_back(A,B);
    }
    // A return branch may meet the middle of a retained long strip. Subdivide
    // only that existing quad, interpolating its exact cross-sections; its union
    // footprint and curve stay unchanged while the T junction gains one phase.
    std::vector<TrailSegment> Subdivided;
    for(size_t I=0;I<Result.size();++I)
    {
        const auto& S=Result[I];const double DX=S.B.X-S.A.X,DY=S.B.Y-S.A.Y,L2=DX*DX+DY*DY,L=std::sqrt(L2);
        std::vector<std::pair<double,size_t>> Cuts{{0.,OriginalNodes[I].first},{1.,OriginalNodes[I].second}};
        for(size_t N=0;N<NodePositions.size();++N)
        {
            const auto& P=NodePositions[N];const double T=((P.X-S.A.X)*DX+(P.Y-S.A.Y)*DY)/L2;
            if(T*L<=.005||(1.-T)*L<=.005)continue;
            if(std::hypot(P.X-S.A.X-T*DX,P.Y-S.A.Y-T*DY)<=.51)Cuts.emplace_back(T,N);
        }
        std::sort(Cuts.begin(),Cuts.end());
        for(size_t C=1;C<Cuts.size();++C)
        {
            const auto [U,A]=Cuts[C-1];const auto [V,B]=Cuts[C];if((V-U)*L<=1.e-7)continue;
            auto At=[&](double T){return Vec{Lerp(S.A.X,S.B.X,T),Lerp(S.A.Y,S.B.Y,T),Lerp(S.A.Z,S.B.Z,T)};};
            Subdivided.push_back({At(U),At(V),0.,(V-U)*S.LengthMeters,
                Lerp(S.StartShearCm,S.EndShearCm,U),Lerp(S.StartShearCm,S.EndShearCm,V),
                Lerp(S.StartHalfWidthCm,S.EndHalfWidthCm,U),Lerp(S.StartHalfWidthCm,S.EndHalfWidthCm,V)});
            SegmentNodes.emplace_back(A,B);const double EdgeLength=(V-U)*S.LengthMeters;
            Edges[A].emplace_back(B,EdgeLength);Edges[B].emplace_back(A,EdgeLength);
        }
    }
    Result=std::move(Subdivided);
    std::vector<double> Phase(Edges.size(),std::numeric_limits<double>::infinity());
    using Candidate=std::pair<double,size_t>;
    for(size_t Root=0;Root<Edges.size();++Root)
    {
        if(std::isfinite(Phase[Root]))continue;
        std::priority_queue<Candidate,std::vector<Candidate>,std::greater<Candidate>> Queue;
        Phase[Root]=0;Queue.emplace(0.,Root);
        while(!Queue.empty())
        {
            const auto [D,N]=Queue.top();Queue.pop();if(D>Phase[N])continue;
            for(const auto& [Other,EdgeLength]:Edges[N])if(D+EdgeLength<Phase[Other])
            {Phase[Other]=D+EdgeLength;Queue.emplace(Phase[Other],Other);}
        }
    }
    for(size_t I=0;I<Result.size();++I)
    {
        const auto [A,B]=SegmentNodes[I];Result[I].StartMeters=Phase[A];
        Result[I].FlowDeltaMeters=Phase[B]-Phase[A];
    }
    return Result;
}
TrailPlan BuildTaskTrail(const Track& Track)
{
    TrailPlan Plan;
    if(Track.Keys.size()<2)return Plan;
    const auto Moving=[](const Key& A,const Key& B)
    {
        return A.Visible&&B.Visible&&B.Time>A.Time&&
            A.Status.find("\xE6\x95\x85\xE9\x9A\x9C")==std::string::npos&&A.Status.find("\xE7\xAD\x89\xE5\xBE\x85")==std::string::npos&&
            std::hypot(B.Position.X-A.Position.X,B.Position.Y-A.Position.Y)>.01;
    };
    auto AddLeg=[&](size_t First,size_t Last)
    {
        if(Last<=First)return;
        GHSReplay::Track Part;
        Part.Keys.assign(Track.Keys.begin()+First,Track.Keys.begin()+Last+1);
        auto Segments=BuildTrailSegments(Part);if(Segments.empty())return;
        TrailLeg Leg;Leg.Id=int(Plan.Legs.size());Leg.StartTime=Track.Keys[First].Time;Leg.EndTime=Track.Keys[Last].Time;
        for(auto& Segment:Segments)
        {
            Segment.LegId=Leg.Id;Segment.ProgressStartMeters=Leg.LengthMeters;Segment.ProgressDeltaMeters=Segment.LengthMeters;
            // Only this directed leg can render. No shared whole-cycle graph or
            // opposite journey is visible at the same time, so flow is monotonic.
            Segment.StartMeters=Leg.LengthMeters;Segment.FlowDeltaMeters=Segment.LengthMeters;
            Leg.LengthMeters+=Segment.LengthMeters;
        }
        double Previous=0.;
        for(size_t I=First;I<=Last;++I)
        {
            double Progress=I==Last?Leg.LengthMeters:0.;
            if(I>First&&I<Last)
            {
                const auto& P=Track.Keys[I].Position;double Best=std::numeric_limits<double>::infinity();Progress=Previous;
                for(const auto& Segment:Segments)
                {
                    const double End=Segment.ProgressStartMeters+Segment.ProgressDeltaMeters;
                    if(End+1.e-9<Previous)continue;
                    const double DX=Segment.B.X-Segment.A.X,DY=Segment.B.Y-Segment.A.Y;
                    const double Minimum=std::clamp((Previous-Segment.ProgressStartMeters)/Segment.ProgressDeltaMeters,0.,1.);
                    const double T=std::clamp(((P.X-Segment.A.X)*DX+(P.Y-Segment.A.Y)*DY)/(DX*DX+DY*DY),Minimum,1.);
                    const double Error=std::hypot(P.X-Segment.A.X-T*DX,P.Y-Segment.A.Y-T*DY);
                    if(Error<Best){Best=Error;Progress=Segment.ProgressStartMeters+Segment.ProgressDeltaMeters*T;}
                }
            }
            Progress=std::clamp(Progress,Previous,Leg.LengthMeters);Leg.DistanceKeys.push_back({Track.Keys[I].Time,Progress});Previous=Progress;
        }
        Plan.Segments.insert(Plan.Segments.end(),Segments.begin(),Segments.end());Plan.Legs.push_back(std::move(Leg));
    };
    size_t First=Track.Keys.size();
    for(size_t I=1;I<Track.Keys.size();++I)
    {
        if(Moving(Track.Keys[I-1],Track.Keys[I])){if(First==Track.Keys.size())First=I-1;}
        else if(First!=Track.Keys.size()){AddLeg(First,I-1);First=Track.Keys.size();}
    }
    if(First!=Track.Keys.size())AddLeg(First,Track.Keys.size()-1);
    return Plan;
}
TrailState EvaluateTaskTrail(const TrailPlan& Plan,double Time,double CycleDuration,double PlaybackEndTime)
{
    TrailState State;if(Plan.Legs.empty())return State;
    Time=std::isfinite(Time)?std::max(0.,Time):0.;
    if(std::isfinite(PlaybackEndTime)&&PlaybackEndTime>=0&&Time>=PlaybackEndTime)return State;
    if(std::isfinite(CycleDuration)&&CycleDuration>0)Time=std::fmod(Time,CycleDuration);
    auto It=std::upper_bound(Plan.Legs.begin(),Plan.Legs.end(),Time,[](double Value,const TrailLeg& Leg){return Value<Leg.StartTime;});
    if(It==Plan.Legs.begin())return State;--It;
    if(Time<It->StartTime||Time>=It->EndTime||It->DistanceKeys.size()<2)return State;
    auto KeyIt=std::upper_bound(It->DistanceKeys.begin(),It->DistanceKeys.end(),Time,[](double Value,const TrailDistanceKey& Key){return Value<Key.Time;});
    const auto& B=KeyIt==It->DistanceKeys.end()?It->DistanceKeys.back():*KeyIt;
    const auto& A=KeyIt==It->DistanceKeys.begin()?It->DistanceKeys.front():*(KeyIt-1);
    const double T=B.Time>A.Time?std::clamp((Time-A.Time)/(B.Time-A.Time),0.,1.):0.;
    State.LegId=It->Id;State.StartTime=It->StartTime;State.EndTime=It->EndTime;State.LengthMeters=It->LengthMeters;
    State.DistanceMeters=std::clamp(Lerp(A.Meters,B.Meters,T),0.,State.LengthMeters);
    State.Moving=State.LengthMeters-State.DistanceMeters>1.e-7;
    return State;
}
bool Simulation::Validate(std::string& Error) const
{
    if(!std::isfinite(CycleDuration)||CycleDuration<60||CycleDuration>86400){Error="Invalid replay cycle duration";return false;}
    std::set<std::string> Ids;
    for(const auto& Track:Tracks)
    {
        if(Track.Id.empty()||!Ids.insert(Track.Id).second||Track.Keys.size()<2||Track.Keys.size()>100000){Error="Invalid replay identity or key count";return false;}
        if(Track.Keys.front().Time!=0||std::abs(Track.Keys.back().Time-CycleDuration)>.001){Error="Incomplete replay track";return false;}
        double Last=-1;
        for(const auto& Key:Track.Keys)
        {
            if(!std::isfinite(Key.Time)||Key.Time<=Last||Key.Time>CycleDuration||!std::isfinite(Key.Position.X)||!std::isfinite(Key.Position.Y)||!std::isfinite(Key.Position.Z)||!std::isfinite(Key.Yaw)||!std::isfinite(Key.Lift)||Key.Owner>=DeviceCount||Key.Owner<-1)
            {Error="Invalid replay key";return false;}
            Last=Key.Time;
        }
        const Key& A=Track.Keys.front();const Key& B=Track.Keys.back();
        if(std::abs(A.Position.X-B.Position.X)>.01||std::abs(A.Position.Y-B.Position.Y)>.01||std::abs(A.Position.Z-B.Position.Z)>.01||std::abs(std::remainder(A.Yaw-B.Yaw,360.))>.01||A.Owner!=B.Owner||A.Visible!=B.Visible)
        {Error="Replay cycle has a discontinuous boundary";return false;}
    }
    double Previous=-1;std::set<std::string> EventIds;
    for(const auto& E:Events)
    {
        if(E.Time<Previous||E.Time<0||E.Time>=CycleDuration||!std::isfinite(E.Time)||E.Id.empty()||!EventIds.insert(E.Id).second||!Ids.count(E.DeviceId)){Error="Invalid event time or identity";return false;}
        Previous=E.Time;
    }
    return true;
}
Pose Simulation::Sample(const Track& Track,double Time)
{
    const auto It=std::upper_bound(Track.Keys.begin(),Track.Keys.end(),Time,[](double T,const Key& K){return T<K.Time;});
    const auto& A=It==Track.Keys.begin()?Track.Keys.front():*(It-1);
    const auto& B=It==Track.Keys.end()?A:*It;
    const double T=B.Time>A.Time&&A.Owner==B.Owner?std::clamp((Time-A.Time)/(B.Time-A.Time),0.,1.):0;
    Pose P;P.Position={Lerp(A.Position.X,B.Position.X,T),Lerp(A.Position.Y,B.Position.Y,T),Lerp(A.Position.Z,B.Position.Z,T)};
    P.Yaw=Angle(A.Yaw,B.Yaw,T);P.Lift=Lerp(A.Lift,B.Lift,T);P.Door=Lerp(A.Door,B.Door,T);
    P.Visible=A.Visible;P.Owner=A.Owner;P.Status=&A.Status;return P;
}
void Simulation::Evaluate(double Time)
{
    if(CycleDuration<=0)return;
    const double Local=std::fmod(std::max(0.,std::isfinite(Time)?Time:0.),CycleDuration);
    for(int I=0;I<EntityCount;++I)Poses[I]=Sample(Tracks[I],Local);
    // Attachments are derived from the same timestamp, never integrated frame-to-frame.
    for(int I=DeviceCount;I<EntityCount;++I)
    {
        auto& P=Poses[I];if(P.Owner<0)continue;
        const auto& Parent=Poses[P.Owner];const double R=Parent.Yaw*3.14159265358979323846/180.;
        const Vec V=P.Position;
        P.Position={Parent.Position.X+std::cos(R)*V.X-std::sin(R)*V.Y,Parent.Position.Y+std::sin(R)*V.X+std::cos(R)*V.Y,Parent.Position.Z+V.Z+(P.Owner<ForkCount?Parent.Lift:0)};
        P.Yaw+=Parent.Yaw;P.Visible=P.Visible&&Parent.Visible;
    }
}
std::vector<Occurrence> Simulation::EventsIn(double Start,double End,int Limit) const
{
    std::vector<Occurrence> Result;
    if(CycleDuration<=0||Events.empty()||!std::isfinite(Start)||!std::isfinite(End)||End<Start||Limit<=0)return Result;
    Limit=std::min(Limit,2048);Result.reserve(std::min(Limit,int(Events.size())));
    const long long First=static_cast<long long>(std::floor(std::max(0.,Start)/CycleDuration));
    const long long Last=static_cast<long long>(std::floor(std::max(0.,End)/CycleDuration));
    for(long long Cycle=First;Cycle<=Last&&int(Result.size())<Limit;++Cycle)
        for(const auto& E:Events)
        {
            const double Time=Cycle*CycleDuration+E.Time;
            if(Time>=Start&&Time<=End)Result.push_back({&E,Time,Cycle});
            if(int(Result.size())>=Limit)break;
        }
    return Result;
}
}
