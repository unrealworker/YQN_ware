#include "GHSOrderReplaySimulation.h"
#include <algorithm>
#include <cmath>
#include <set>
#include <map>
#include <functional>

namespace GHSReplay
{
static double Lerp(double A,double B,double T){return A+(B-A)*T;}
static double Angle(double A,double B,double T){return A+std::remainder(B-A,360.)*T;}
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
            if(B<=A+1)return;double Maximum=1.;size_t Split=B;
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
        size_t Previous=0;
        for(size_t I=1;I<Run.size();++I)if(Keep[I])
        {
            const Vec A=Run[Previous],B=Run[I];Previous=I;const double L=Length(A,B);if(L<.01)continue;
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
                Result.push_back({At(U),At(V),DistanceMeters+U*L/100.,(V-U)*L/100.});
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
        if(!A.Visible||!B.Visible||Length(A.Position,B.Position)<.01){Flush();continue;}
        if(Run.empty())Run.push_back(A.Position);Run.push_back(B.Position);
    }
    Flush();return Result;
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
