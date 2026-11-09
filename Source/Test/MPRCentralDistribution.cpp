#include "MPRCentralDistribution.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace MPRCentral
{
namespace
{
constexpr double PositionTolerance=1.e-10,TimeTolerance=1.e-10;
double Wrap(double V) {V-=std::floor(V);return V<PositionTolerance||1.-V<PositionTolerance?0.:V;}
double ForwardDistance(double From,double To) {double D=To-From;if(D<-PositionTolerance)D+=1.;return std::max(0.,D);}
bool Positive(double V) {return std::isfinite(V)&&V>0.;}
}
bool Simulation::Initialize(const Config& C,std::string& Error)
{
    Error.clear();
    if(C.CarrierCount<1||C.CarrierCount>256||C.FeedDistances01.empty()||C.FeedDistances01.size()>64
       ||C.TargetDistances01.empty()||C.TargetDistances01.size()>256)
        Error="Invalid bounded carrier, source or destination count.";
    else if(!Positive(C.LoopLengthCm)||C.LoopLengthCm<100||C.LoopLengthCm>100000
         ||!Positive(C.SpeedCmS)||C.SpeedCmS>1000||!Positive(C.LoadingSeconds)||C.LoadingSeconds<.01||C.LoadingSeconds>3600
         ||!Positive(C.TransferSeconds)||C.TransferSeconds<.01||C.TransferSeconds>3600
         ||!Positive(C.RecoverySeconds)||C.RecoverySeconds<.01||C.RecoverySeconds>3600)
        Error="Invalid loop geometry or station durations.";
    if(!Error.empty())return false;
    std::vector<Stop> NewStops;
    for(size_t I=0;I<C.FeedDistances01.size();++I)NewStops.push_back({C.FeedDistances01[I],int(I),-1});
    for(size_t I=0;I<C.TargetDistances01.size();++I)NewStops.push_back({C.TargetDistances01[I],-1,int(I)});
    for(const auto& S:NewStops)if(!std::isfinite(S.Distance01)||S.Distance01<0||S.Distance01>=1)
    {Error="Each station distance must be finite and inside [0,1).";return false;}
    std::sort(NewStops.begin(),NewStops.end(),[](const Stop& A,const Stop& B){return A.Distance01<B.Distance01;});
    for(size_t I=0;I<NewStops.size();++I)
    {
        double Gap=I?NewStops[I].Distance01-NewStops[I-1].Distance01:NewStops.front().Distance01+1.-NewStops.back().Distance01;
        if(Gap<1.e-6){Error="Loading and branch stations must occupy distinct loop positions.";return false;}
    }
    Settings=C;Stops=std::move(NewStops);Ready=true;Reset();return true;
}
void Simulation::Reset()
{
    Playing=false;Totals={};NextTarget=0;Carriers.clear();NextStops.clear();Elapsed.clear();
    if(!Ready)return;
    for(int I=0;I<Settings.CarrierCount;++I)
    {
        Carrier C;C.Distance01=double(I)/Settings.CarrierCount;Carriers.push_back(C);Elapsed.push_back(0.);
        size_t Next=0;
        while(Next<Stops.size()&&Stops[Next].Distance01<C.Distance01-PositionTolerance)++Next;
        NextStops.push_back(Next==Stops.size()?0:Next);
    }
}
bool Simulation::HasDwell() const
{
    for(const auto& C:Carriers)if(C.Phase==CarrierPhase::Loading||C.Phase==CarrierPhase::Discharging
        ||C.Phase==CarrierPhase::Retracting||C.Phase==CarrierPhase::Recovering)return true;
    return false;
}
int Simulation::FindTarget() const
{
    // One reservation per sorter also guarantees its external ID order when
    // different destinations wait for different numbers of circulation laps.
    for(size_t I=0;I<Settings.TargetDistances01.size();++I)
    {
        int Target=(NextTarget+int(I))%int(Settings.TargetDistances01.size());bool Busy=false;
        for(const auto& C:Carriers)if(C.TargetIndex==Target){Busy=true;break;}
        if(!Busy)return Target;
    }
    return -1;
}
void Simulation::SettleEvents(uint64_t& NextGlobalParcelId,const CanAcceptCallback& CanAccept,const AcceptCallback& Accept)
{
    for(size_t I=0;I<Carriers.size();++I)
    {
        auto& C=Carriers[I];
        if(C.Phase==CarrierPhase::Loading&&Elapsed[I]>=Settings.LoadingSeconds-TimeTolerance)
        {C.Phase=CarrierPhase::Travel;C.Progress01=0;Elapsed[I]=0;}
        else if(C.Phase==CarrierPhase::Discharging&&Elapsed[I]>=Settings.TransferSeconds-TimeTolerance)
        {
            if(CanAccept(C.TargetIndex)&&Accept(C.TargetIndex,C.ParcelId))
            {++Totals.Delivered;--Totals.Active;C.ParcelId=0;C.Phase=CarrierPhase::Recovering;}
            else {++Totals.BlockedPasses;C.Phase=CarrierPhase::Retracting;}
            C.Progress01=0;Elapsed[I]=0;
        }
        else if(C.Phase==CarrierPhase::Retracting&&Elapsed[I]>=Settings.TransferSeconds-TimeTolerance)
        {C.Phase=CarrierPhase::Travel;C.Progress01=0;Elapsed[I]=0;}
        else if(C.Phase==CarrierPhase::Recovering&&Elapsed[I]>=Settings.RecoverySeconds-TimeTolerance)
        {C.Phase=CarrierPhase::EmptyReturn;C.TargetIndex=-1;C.SourceStation=-1;C.Progress01=0;Elapsed[I]=0;}
    }
    // Process every simultaneous arrival before deciding whether the shared
    // chain stops. Each stop is consumed once even when admission is blocked.
    for(size_t I=0;I<Carriers.size();++I)
    {
        auto& C=Carriers[I];const auto& S=Stops[NextStops[I]];
        if(ForwardDistance(C.Distance01,S.Distance01)>PositionTolerance)continue;
        NextStops[I]=(NextStops[I]+1)%Stops.size();
        if(C.Phase==CarrierPhase::EmptyReturn&&S.SourceStation>=0&&NextGlobalParcelId)
        {
            int Target=FindTarget();if(Target<0)continue;
            C.ParcelId=NextGlobalParcelId;NextGlobalParcelId=NextGlobalParcelId==std::numeric_limits<uint64_t>::max()?0:NextGlobalParcelId+1;
            C.TargetIndex=Target;C.SourceStation=S.SourceStation;C.Phase=CarrierPhase::Loading;C.Progress01=0;Elapsed[I]=0;
            NextTarget=(Target+1)%int(Settings.TargetDistances01.size());++Totals.Generated;++Totals.Active;
        }
        else if(C.Phase==CarrierPhase::Travel&&S.TargetIndex==C.TargetIndex)
        {
            if(CanAccept(C.TargetIndex)){C.Phase=CarrierPhase::Discharging;C.Progress01=0;Elapsed[I]=0;}
            else ++Totals.BlockedPasses;
        }
    }
    Totals.LoopStopped=HasDwell();
}
double Simulation::NextEventSeconds() const
{
    double Next=std::numeric_limits<double>::infinity();
    if(HasDwell())
    {
        for(size_t I=0;I<Carriers.size();++I)
        {
            if(Carriers[I].Phase==CarrierPhase::Loading)Next=std::min(Next,Settings.LoadingSeconds-Elapsed[I]);
            if(Carriers[I].Phase==CarrierPhase::Discharging||Carriers[I].Phase==CarrierPhase::Retracting)
                Next=std::min(Next,Settings.TransferSeconds-Elapsed[I]);
            if(Carriers[I].Phase==CarrierPhase::Recovering)Next=std::min(Next,Settings.RecoverySeconds-Elapsed[I]);
        }
    }
    else for(size_t I=0;I<Carriers.size();++I)
        Next=std::min(Next,ForwardDistance(Carriers[I].Distance01,Stops[NextStops[I]].Distance01)*Settings.LoopLengthCm/Settings.SpeedCmS);
    return Next;
}
void Simulation::Integrate(double Seconds)
{
    Totals.SimTime+=Seconds;const bool Stopped=HasDwell();
    if(!Stopped)Totals.LoopPhase01=Wrap(Totals.LoopPhase01+Seconds*Settings.SpeedCmS/Settings.LoopLengthCm);
    for(size_t I=0;I<Carriers.size();++I)
    {
        auto& C=Carriers[I];
        if(!Stopped)C.Distance01=Wrap(Totals.LoopPhase01+double(I)/Settings.CarrierCount);
        else if(C.Phase==CarrierPhase::Loading||C.Phase==CarrierPhase::Discharging
            ||C.Phase==CarrierPhase::Retracting||C.Phase==CarrierPhase::Recovering)
        {
            const double Duration=C.Phase==CarrierPhase::Loading?Settings.LoadingSeconds:
                C.Phase==CarrierPhase::Recovering?Settings.RecoverySeconds:Settings.TransferSeconds;
            Elapsed[I]+=Seconds;C.Progress01=std::min(1.,Elapsed[I]/Duration);
        }
    }
}
bool Simulation::Advance(double Seconds,uint64_t& NextGlobalParcelId,const CanAcceptCallback& CanAccept,const AcceptCallback& Accept)
{
    if(!Ready||!std::isfinite(Seconds)||Seconds<0||Seconds>86400||!CanAccept||!Accept)return false;
    if(!Playing||Seconds==0)return true;
    SettleEvents(NextGlobalParcelId,CanAccept,Accept);
    double Remaining=Seconds;
    while(Remaining>0.)
    {
        const double Step=std::min(Remaining,NextEventSeconds());
        if(!Positive(Step))return false;
        Integrate(Step);Remaining=std::max(0.,Remaining-Step);SettleEvents(NextGlobalParcelId,CanAccept,Accept);
    }
    return true;
}
}
