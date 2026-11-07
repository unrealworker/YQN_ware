#include "MPRSorterSimulation.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace MPRSorter
{
namespace
{
constexpr double PositionTolerance=1.e-10,HeightTolerance=1.e-7,TimeTolerance=1.e-10;
double Wrap(double Value)
{
    Value-=std::floor(Value);
    return Value<PositionTolerance||1.-Value<PositionTolerance?0.:Value;
}
double ForwardDistance(double From,double To)
{
    double Distance=To-From;
    if(Distance<-PositionTolerance)Distance+=1.;
    return std::max(0.,Distance);
}
bool IsPositive(double Value) {return std::isfinite(Value)&&Value>0.;}
bool IsDestination(const Config& C,Destination D)
{return D.Side>=0&&D.Side<2&&D.Column>=0&&D.Column<C.Columns&&D.Level>=0&&D.Level<C.Levels;}
}

bool Simulation::Initialize(const Config& C,std::string& Error)
{
    Error.clear();
    if(C.Columns<1||C.Columns>64||C.Levels<1||C.Levels>8||C.BinCapacity<1||C.BinCapacity>10000)
        Error="Columns, levels or bin capacity is outside the bounded demonstration profile.";
    else if(!IsPositive(C.LoopLengthCm)||C.LoopLengthCm<100||C.LoopLengthCm>100000
        ||!IsPositive(C.ChainSpeedCmS)||C.ChainSpeedCmS>1000
        ||!IsPositive(C.LiftSpeedCmS)||C.LiftSpeedCmS>1000
        ||!std::isfinite(C.LoadHeightCm)||C.LoadHeightCm<0||C.LoadHeightCm>10000)
        Error="Loop length, chain speed or lift geometry is invalid.";
    else if(!IsPositive(C.ScanSeconds)||C.ScanSeconds<.01||C.ScanSeconds>3600
        ||!IsPositive(C.UnloadSeconds)||C.UnloadSeconds<.01||C.UnloadSeconds>3600
        ||!IsPositive(C.CollectSeconds)||C.CollectSeconds<.01||C.CollectSeconds>86400)
        Error="Scan, unloading and simulated collection durations must be finite and bounded.";
    else if(C.LevelHeightsCm.size()!=size_t(C.Levels)||C.DestinationDistances01.size()!=size_t(C.Columns*2))
        Error="The profile must explicitly provide every destination and height.";
    if(!Error.empty())return false;
    for(double Height:C.LevelHeightsCm)
        if(!std::isfinite(Height)||Height<0||Height>10000) {Error="Invalid target height.";return false;}
    for(size_t I=0;I<C.DestinationDistances01.size();++I)
    {
        const double D=C.DestinationDistances01[I];
        if(!std::isfinite(D)||D<=1.e-6||D>=1.-1.e-6) {Error="Destination must lie strictly after load and before the loop returns.";return false;}
        for(size_t J=0;J<I;++J)
            if(std::abs(D-C.DestinationDistances01[J])<1.e-6) {Error="Distinct columns/sides must not share one station.";return false;}
    }
    if(C.OrderSequence.size()>65536) {Error="Demonstration order sequence is too large.";return false;}
    for(const auto& D:C.OrderSequence)
        if(!IsDestination(C,D)) {Error="Demonstration order has an invalid destination.";return false;}
    Settings=C;Ready=true;Reset();return true;
}

int Simulation::BinIndex(Destination D) const
{
    return Ready&&IsDestination(Settings,D)?(D.Side*Settings.Columns+D.Column)*Settings.Levels+D.Level:-1;
}

void Simulation::Reset()
{
    Playing=false;Rate=1.;AutoCollect=Settings.AutoCollect;
    Totals={};NextParcelId=1;NextOrder=0;PhaseElapsed.fill(0.);
    for(int I=0;I<CarrierCount;++I)
    {Carriers[I]={};Carriers[I].Distance01=double(I)/CarrierCount;Carriers[I].LiftHeightCm=Settings.LoadHeightCm;}
    Bins.clear();
    if(!Ready)return;
    Bins.reserve(size_t(2*Settings.Columns*Settings.Levels));
    for(int Side=0;Side<2;++Side)for(int Column=0;Column<Settings.Columns;++Column)for(int Level=0;Level<Settings.Levels;++Level)
    {Bin B;B.Target={Side,Column,Level};B.Capacity=Settings.BinCapacity;Bins.push_back(B);}
    RefreshStatus();
}

bool Simulation::SetRate(double Value)
{
    if(Value!=1.&&Value!=2.&&Value!=4.)return false;
    Rate=Value;return true;
}

void Simulation::SetAutoCollect(bool Value)
{
    if(AutoCollect==Value)return;
    AutoCollect=Value;
    // Re-enabling starts a full visible operator interval, without backdating a pickup.
    if(Value)for(auto& B:Bins)if(B.Occupancy>0)B.CollectionRemaining=Settings.CollectSeconds;
}

bool Simulation::ClearBin(Destination Target)
{
    const int Index=BinIndex(Target);if(Index<0)return false;
    auto& B=Bins[size_t(Index)];
    // Keep the whole receiving bin stable throughout an incoming unload. Its
    // occupied stack is also the resting position of the animated parcel.
    if(B.Reserved>0)return false;
    B.Collected+=uint64_t(B.Occupancy);Totals.Collected+=uint64_t(B.Occupancy);
    B.Occupancy=0;B.CollectionRemaining=0;
    RefreshStatus();return true;
}

Destination Simulation::NextDestination()
{
    const uint64_t Index=NextOrder++;
    if(!Settings.OrderSequence.empty())return Settings.OrderSequence[size_t(Index%Settings.OrderSequence.size())];
    const uint64_t N=Index%uint64_t(2*Settings.Columns*Settings.Levels);
    return {int(N%2),int(N/uint64_t(2*Settings.Levels)),int((N/2)%uint64_t(Settings.Levels))};
}

bool Simulation::AtLoad(const Carrier& Item) const
{return Item.Distance01<=PositionTolerance||1.-Item.Distance01<=PositionTolerance;}
double Simulation::TargetHeight(const Carrier& Item) const
{
    return Item.State==CarrierPhase::EmptyReturn||Item.State==CarrierPhase::Scan
        ?Settings.LoadHeightCm:Settings.LevelHeightsCm[size_t(Item.Target.Level)];
}
double Simulation::TargetDistance(const Carrier& Item) const
{return Settings.DestinationDistances01[size_t(Item.Target.Side*Settings.Columns+Item.Target.Column)];}

void Simulation::SettleEvents()
{
    // No time elapses here. Repeating resolves simultaneous arrival, height, capacity,
    // scan and unload boundaries independent of how callers partition frame deltas.
    bool Changed=true;
    while(Changed)
    {
        Changed=false;
        if(AutoCollect)for(auto& B:Bins)if(B.Occupancy>0&&B.Reserved==0&&B.CollectionRemaining<=TimeTolerance)
        {if(ClearBin(B.Target))Changed=true;}
        for(int I=0;I<CarrierCount;++I)
        {
            auto& C=Carriers[I];
            switch(C.State)
            {
            case CarrierPhase::EmptyReturn:
                if(AtLoad(C)&&std::abs(C.LiftHeightCm-Settings.LoadHeightCm)<=HeightTolerance)
                {
                    C.LiftHeightCm=Settings.LoadHeightCm;C.State=CarrierPhase::Scan;
                    C.ParcelId=NextParcelId++;C.Target=NextDestination();C.ScanProgress=0;C.UnloadProgress=0;
                    PhaseElapsed[I]=0;++Totals.Spawned;Changed=true;
                }
                break;
            case CarrierPhase::Scan:
                if(PhaseElapsed[I]>=Settings.ScanSeconds-TimeTolerance)
                {C.ScanProgress=1.;C.State=CarrierPhase::LoadedTravel;PhaseElapsed[I]=0;Changed=true;}
                break;
            case CarrierPhase::LoadedTravel:
                if(std::abs(C.Distance01-TargetDistance(C))<=PositionTolerance)
                {C.State=CarrierPhase::Lift;PhaseElapsed[I]=0;Changed=true;}
                break;
            case CarrierPhase::Lift:
            {
                auto& B=Bins[size_t(BinIndex(C.Target))];
                if(std::abs(C.LiftHeightCm-TargetHeight(C))<=HeightTolerance&&B.Occupancy+B.Reserved<B.Capacity)
                {
                    C.LiftHeightCm=TargetHeight(C);C.State=CarrierPhase::Unload;
                    C.UnloadProgress=0;PhaseElapsed[I]=0;++B.Reserved;Changed=true;
                }
                break;
            }
            case CarrierPhase::Unload:
                if(PhaseElapsed[I]>=Settings.UnloadSeconds-TimeTolerance)
                {
                    auto& B=Bins[size_t(BinIndex(C.Target))];
                    --B.Reserved;if(B.Occupancy==0)B.CollectionRemaining=Settings.CollectSeconds;
                    ++B.Occupancy;++B.Delivered;++Totals.Completed;
                    C.ParcelId=0;C.State=CarrierPhase::EmptyReturn;C.ScanProgress=0;C.UnloadProgress=0;
                    PhaseElapsed[I]=0;Changed=true;
                }
                break;
            }
        }
    }
    RefreshStatus();
}

void Simulation::RefreshStatus()
{
    Totals.Active=0;Totals.Reason=BlockReason::None;
    bool Scanning=false,Lifting=false,Unloading=false,Full=false;
    for(const auto& C:Carriers)
    {
        if(C.ParcelId)++Totals.Active;
        Scanning|=C.State==CarrierPhase::Scan;
        Unloading|=C.State==CarrierPhase::Unload;
        if(C.State==CarrierPhase::Lift)
        {
            const auto& B=Bins[size_t(BinIndex(C.Target))];
            Full|=B.Occupancy+B.Reserved>=B.Capacity;
            Lifting=true;
        }
        if(C.State==CarrierPhase::EmptyReturn&&AtLoad(C)&&std::abs(C.LiftHeightCm-Settings.LoadHeightCm)>HeightTolerance)Lifting=true;
    }
    if(Full)Totals.Reason=BlockReason::FullBin;
    else if(Lifting)Totals.Reason=BlockReason::Lifting;
    else if(Scanning)Totals.Reason=BlockReason::Scanning;
    else if(Unloading)Totals.Reason=BlockReason::Unloading;
    Totals.ChainStopped=Totals.Reason!=BlockReason::None;
}

double Simulation::NextEventSeconds(bool MoveChain) const
{
    double Next=std::numeric_limits<double>::infinity();
    const double Velocity=Settings.ChainSpeedCmS/Settings.LoopLengthCm;
    for(int I=0;I<CarrierCount;++I)
    {
        const auto& C=Carriers[I];
        if(MoveChain)
        {
            const double Distance=C.State==CarrierPhase::EmptyReturn?ForwardDistance(C.Distance01,0.):ForwardDistance(C.Distance01,TargetDistance(C));
            Next=std::min(Next,Distance/Velocity);
        }
        const double Height=std::abs(TargetHeight(C)-C.LiftHeightCm);
        if(Height>HeightTolerance)Next=std::min(Next,Height/Settings.LiftSpeedCmS);
        if(C.State==CarrierPhase::Scan)Next=std::min(Next,Settings.ScanSeconds-PhaseElapsed[I]);
        if(C.State==CarrierPhase::Unload)Next=std::min(Next,Settings.UnloadSeconds-PhaseElapsed[I]);
    }
    // An expired pickup with an active reservation waits for unload completion;
    // including its zero timer again would prevent simulation time advancing.
    if(AutoCollect)for(const auto& B:Bins)
        if(B.Occupancy>0&&(B.Reserved==0||B.CollectionRemaining>TimeTolerance))
            Next=std::min(Next,B.CollectionRemaining);
    return Next;
}

void Simulation::Integrate(double Seconds,bool MoveChain)
{
    Totals.SimTime+=Seconds;
    if(MoveChain)Totals.ChainPhase01=Wrap(Totals.ChainPhase01+Settings.ChainSpeedCmS*Seconds/Settings.LoopLengthCm);
    else Totals.BlockedSeconds+=Seconds;
    for(int I=0;I<CarrierCount;++I)
    {
        auto& C=Carriers[I];
        C.Distance01=Wrap(Totals.ChainPhase01+double(I)/CarrierCount);
        const double Delta=TargetHeight(C)-C.LiftHeightCm,Move=Settings.LiftSpeedCmS*Seconds;
        C.LiftHeightCm+=std::clamp(Delta,-Move,Move);
        if(C.State==CarrierPhase::Scan)
        {PhaseElapsed[I]+=Seconds;C.ScanProgress=std::min(1.,PhaseElapsed[I]/Settings.ScanSeconds);}
        if(C.State==CarrierPhase::Unload)
        {PhaseElapsed[I]+=Seconds;C.UnloadProgress=std::min(1.,PhaseElapsed[I]/Settings.UnloadSeconds);}
    }
    if(AutoCollect)for(auto& B:Bins)if(B.Occupancy>0)B.CollectionRemaining=std::max(0.,B.CollectionRemaining-Seconds);
}

bool Simulation::Advance(double WallDeltaSeconds)
{
    if(!Ready||!std::isfinite(WallDeltaSeconds)||WallDeltaSeconds<0||WallDeltaSeconds>86400./Rate)return false;
    if(!Playing||WallDeltaSeconds==0)return true;
    double Remaining=WallDeltaSeconds*Rate;
    SettleEvents();
    while(Remaining>0.)
    {
        const bool MoveChain=!Totals.ChainStopped;
        const double Step=std::min(Remaining,NextEventSeconds(MoveChain));
        // Settled events guarantee a positive next event interval. This also guards
        // against a malformed arithmetic state rather than silently dropping time.
        if(!(Step>0.)||!std::isfinite(Step))return false;
        Integrate(Step,MoveChain);
        Remaining=std::max(0.,Remaining-Step);
        SettleEvents();
    }
    return true;
}
}
