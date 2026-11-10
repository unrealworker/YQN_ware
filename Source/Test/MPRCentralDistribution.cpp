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
    if(C.CarrierCount<1||C.CarrierCount>256||C.MaxPendingPerTarget<1||C.MaxPendingPerTarget>256||C.FeedDistances01.empty()||C.FeedDistances01.size()>64
       ||C.TargetDistances01.empty()||C.TargetDistances01.size()>256)
        Error="Invalid bounded carrier, source or destination count.";
    else if(!Positive(C.LoopLengthCm)||C.LoopLengthCm<100||C.LoopLengthCm>100000
         ||!Positive(C.SpeedCmS)||C.SpeedCmS>1000||!Positive(C.LoadingSeconds)||C.LoadingSeconds<.01||C.LoadingSeconds>3600
         ||!Positive(C.TransferSeconds)||C.TransferSeconds<.01||C.TransferSeconds>3600
         ||!Positive(C.RecoverySeconds)||C.RecoverySeconds<.01||C.RecoverySeconds>3600
         ||!Positive(C.FeedHandoffProgress)||C.FeedHandoffProgress>1.)
        Error="Invalid loop geometry or station durations.";
    if(!Error.empty())return false;
    std::vector<Stop> NewStops;
    for(double D:C.FeedDistances01)if(!std::isfinite(D)||D<0||D>=1)
    {Error="Each station distance must be finite and inside [0,1).";return false;}
    for(double D:C.TargetDistances01)if(!std::isfinite(D)||D<0||D>=1)
    {Error="Each station distance must be finite and inside [0,1).";return false;}
    std::vector<double> Ports=C.FeedDistances01;Ports.insert(Ports.end(),C.TargetDistances01.begin(),C.TargetDistances01.end());
    std::sort(Ports.begin(),Ports.end());
    for(size_t I=0;I<Ports.size();++I)
    {
        double Gap=I?Ports[I]-Ports[I-1]:Ports.front()+1.-Ports.back();
        if(Gap<1.e-6){Error="Loading and branch stations must occupy distinct loop positions.";return false;}
    }
    for(size_t I=0;I<C.FeedDistances01.size();++I)NewStops.push_back({Wrap(C.FeedDistances01[I]-C.SpeedCmS*C.LoadingSeconds*C.FeedHandoffProgress/C.LoopLengthCm),int(I),-1});
    for(size_t I=0;I<C.TargetDistances01.size();++I)NewStops.push_back({Wrap(C.TargetDistances01[I]-C.SpeedCmS*C.TransferSeconds/C.LoopLengthCm),-1,int(I)});
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
    Playing=false;FeedingEnabled=true;Totals={};Totals.LoopStopped=true;NextTarget=0;Carriers.clear();NextStops.clear();Elapsed.clear();
    if(!Ready)return;
    FeedCounts.assign(Settings.FeedDistances01.size(),0);
    for(int I=0;I<Settings.CarrierCount;++I)
    {
        Carrier C;C.Distance01=double(I)/Settings.CarrierCount;Carriers.push_back(C);Elapsed.push_back(0.);
        size_t Next=0;
        while(Next<Stops.size()&&Stops[Next].Distance01<C.Distance01-PositionTolerance)++Next;
        NextStops.push_back(Next==Stops.size()?0:Next);
    }
}
Carrier Simulation::GetPresentationCarrier(size_t Index,double ResidualSeconds) const
{
    if(Index>=Carriers.size())return {};
    Carrier C=Carriers[Index];
    const double Delta=std::isfinite(ResidualSeconds)?std::clamp(ResidualSeconds,0.,FleetStepSeconds):0.;
    C.Distance01=Wrap(C.Distance01+Delta*Settings.SpeedCmS/Settings.LoopLengthCm);
    if(C.Phase==CarrierPhase::Loading||C.Phase==CarrierPhase::Discharging
        ||C.Phase==CarrierPhase::Retracting||C.Phase==CarrierPhase::Recovering)
    {
        const double Duration=C.Phase==CarrierPhase::Loading?Settings.LoadingSeconds:
            C.Phase==CarrierPhase::Recovering?Settings.RecoverySeconds:Settings.TransferSeconds;
        // Waiting at a completed local transfer is preferable to predicting a
        // delivery which the destination may reject at the next logical tick.
        C.Progress01=std::min(1.,C.Progress01+Delta/Duration);
    }
    return C;
}
bool Simulation::IsOldestForTarget(const Carrier& C) const
{
    for(const auto& Other:Carriers)if(Other.ParcelId&&Other.TargetIndex==C.TargetIndex&&Other.ParcelId<C.ParcelId)return false;
    return true;
}
bool Simulation::CanFeedAt(int Source) const
{
    if(!FeedingEnabled)return false;
    for(const auto& C:Carriers)if(C.Phase==CarrierPhase::Loading&&C.SourceStation==Source)return false;
    // Give all CAD operators work instead of letting the first upstream port
    // fill every empty tray. Counts differ by at most one complete work round.
    return FeedCounts[Source]==*std::min_element(FeedCounts.begin(),FeedCounts.end());
}
double Simulation::EarliestHandoffSeconds(size_t CarrierIndex,int Target) const
{
    const auto& C=Carriers[CarrierIndex];
    if(C.Phase==CarrierPhase::Discharging)return Settings.TransferSeconds-Elapsed[CarrierIndex];
    const double Cycle=Settings.LoopLengthCm/Settings.SpeedCmS;
    const double Start=Wrap(Settings.TargetDistances01[Target]-Settings.TransferSeconds/Cycle);
    double Arrival=ForwardDistance(C.Distance01,Start)*Cycle;
    const double Busy=C.Phase==CarrierPhase::Loading?Settings.LoadingSeconds-Elapsed[CarrierIndex]:
        C.Phase==CarrierPhase::Retracting?Settings.TransferSeconds-Elapsed[CarrierIndex]:0.;
    if(Arrival<Busy-TimeTolerance)Arrival+=std::ceil((Busy-Arrival)/Cycle)*Cycle;
    return Arrival+Settings.TransferSeconds;
}
int Simulation::FindTarget(const Carrier& Incoming,const CanAcceptCallback& CanAccept) const
{
    for(size_t I=0;I<Settings.TargetDistances01.size();++I)
    {
        int Target=(NextTarget+int(I))%int(Settings.TargetDistances01.size()),Pending=0;double LastHandoff=0;
        for(size_t J=0;J<Carriers.size();++J)if(Carriers[J].ParcelId&&Carriers[J].TargetIndex==Target)
        {++Pending;LastHandoff=std::max(LastHandoff,EarliestHandoffSeconds(J,Target));}
        if(Pending>=Settings.MaxPendingPerTarget||!CanAccept(Target))continue;
        const double Cycle=Settings.LoopLengthCm/Settings.SpeedCmS;
        const double Start=Wrap(Settings.TargetDistances01[Target]-Settings.TransferSeconds/Cycle);
        double Arrival=ForwardDistance(Incoming.Distance01,Start)*Cycle;
        if(Arrival<Settings.LoadingSeconds-TimeTolerance)Arrival+=std::ceil((Settings.LoadingSeconds-Arrival)/Cycle)*Cycle;
        // An upstream source must not send a later ID ahead of an older parcel
        // from the opposite end, forcing an avoidable full recirculation lap.
        if(Arrival+TimeTolerance>=LastHandoff)return Target;
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
    // Every station crossing is consumed exactly once while timed operations
    // run concurrently. No carrier phase can stop the shared chain.
    for(size_t I=0;I<Carriers.size();++I)
    {
        auto& C=Carriers[I];const auto& S=Stops[NextStops[I]];
        if(ForwardDistance(C.Distance01,S.Distance01)>PositionTolerance)continue;
        NextStops[I]=(NextStops[I]+1)%Stops.size();
        if(C.Phase==CarrierPhase::EmptyReturn&&S.SourceStation>=0&&NextGlobalParcelId&&CanFeedAt(S.SourceStation))
        {
            int Target=FindTarget(C,CanAccept);if(Target<0)continue;
            C.ParcelId=NextGlobalParcelId;NextGlobalParcelId=NextGlobalParcelId==std::numeric_limits<uint64_t>::max()?0:NextGlobalParcelId+1;
            C.TargetIndex=Target;C.SourceStation=S.SourceStation;C.Phase=CarrierPhase::Loading;C.Progress01=0;Elapsed[I]=0;
            NextTarget=(Target+1)%int(Settings.TargetDistances01.size());++Totals.Generated;++Totals.Active;++FeedCounts[S.SourceStation];
        }
        else if(C.Phase==CarrierPhase::Travel&&S.TargetIndex==C.TargetIndex)
        {
            if(IsOldestForTarget(C)&&CanAccept(C.TargetIndex)){C.Phase=CarrierPhase::Discharging;C.Progress01=0;Elapsed[I]=0;}
            else ++Totals.BlockedPasses;
        }
    }
    Totals.LoopStopped=!Playing;
}
double Simulation::NextEventSeconds() const
{
    double Next=std::numeric_limits<double>::infinity();
    for(size_t I=0;I<Carriers.size();++I)
    {
        if(Carriers[I].Phase==CarrierPhase::Loading)Next=std::min(Next,Settings.LoadingSeconds-Elapsed[I]);
        if(Carriers[I].Phase==CarrierPhase::Discharging||Carriers[I].Phase==CarrierPhase::Retracting)
            Next=std::min(Next,Settings.TransferSeconds-Elapsed[I]);
        if(Carriers[I].Phase==CarrierPhase::Recovering)Next=std::min(Next,Settings.RecoverySeconds-Elapsed[I]);
        Next=std::min(Next,ForwardDistance(Carriers[I].Distance01,Stops[NextStops[I]].Distance01)*Settings.LoopLengthCm/Settings.SpeedCmS);
    }
    return Next;
}
void Simulation::Integrate(double Seconds)
{
    Totals.SimTime+=Seconds;
    Totals.LoopPhase01=Wrap(Totals.LoopPhase01+Seconds*Settings.SpeedCmS/Settings.LoopLengthCm);
    for(size_t I=0;I<Carriers.size();++I)
    {
        auto& C=Carriers[I];
        C.Distance01=Wrap(Totals.LoopPhase01+double(I)/Settings.CarrierCount);
        if(C.Phase==CarrierPhase::Loading||C.Phase==CarrierPhase::Discharging
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
