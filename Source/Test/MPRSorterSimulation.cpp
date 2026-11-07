#include "MPRSorterSimulation.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace MPRSorter
{
namespace
{
constexpr double PositionTolerance=1.e-10,HeightTolerance=1.e-7,TimeTolerance=1.e-10;
double Wrap(double V) {V-=std::floor(V);return V<PositionTolerance||1.-V<PositionTolerance?0.:V;}
double ForwardDistance(double A,double B) {double D=B-A;if(D<-PositionTolerance)D+=1.;return std::max(0.,D);}
bool Positive(double V) {return std::isfinite(V)&&V>0.;}
bool ValidDestination(const Config& C,Destination D)
{return D.Side>=0&&D.Side<2&&D.Column>=0&&D.Column<C.Columns&&D.Level>=0&&D.Level<C.Levels;}
}

bool Simulation::Initialize(const Config& C,std::string& Error)
{
    Error.clear();
    if(C.Columns<1||C.Columns>64||C.Levels<1||C.Levels>8||C.BinCapacity<1||C.BinCapacity>10000
       ||C.CartColumns<1||C.CartColumns>64||C.InfeedCapacity<1||C.InfeedCapacity>256)
        Error="Invalid bounded scene, cart grouping or infeed capacity.";
    else if(!Positive(C.LoopLengthCm)||C.LoopLengthCm<100||C.LoopLengthCm>100000
         ||!Positive(C.ChainSpeedCmS)||C.ChainSpeedCmS>1000||!Positive(C.LiftSpeedCmS)||C.LiftSpeedCmS>1000
         ||!std::isfinite(C.LoadHeightCm)||C.LoadHeightCm<0||C.LoadHeightCm>10000)
        Error="Invalid loop or lift geometry.";
    else if(C.LevelHeightsCm.size()!=size_t(C.Levels)||C.DestinationDistances01.size()!=size_t(C.Columns*2))
        Error="Every station and height must be explicit.";
    if(!Error.empty())return false;
    for(double V:{C.ScanSeconds,C.UnloadSeconds,C.CollectSeconds,C.InfeedTravelSeconds,C.InfeedSpacingSeconds,
                  C.InductSeconds,C.CartWithdrawSeconds,C.CartOutboundSeconds,C.CartEmptyArrivalSeconds,C.CartDockSeconds,C.CartHandoffSeconds})
        if(!Positive(V)||V<.01||V>3600) {Error="Durations must be finite, positive and bounded.";return false;}
    for(double V:C.LevelHeightsCm)if(!std::isfinite(V)||V<0||V>10000) {Error="Invalid target height.";return false;}
    for(size_t I=0;I<C.DestinationDistances01.size();++I)
    {
        double V=C.DestinationDistances01[I];
        if(!std::isfinite(V)||V<=1.e-6||V>=1.-1.e-6) {Error="Station must be strictly inside the loop.";return false;}
        for(size_t J=0;J<I;++J)if(std::abs(V-C.DestinationDistances01[J])<1.e-6)
        {Error="Stations cannot coincide.";return false;}
    }
    if(C.OrderSequence.size()>65536) {Error="Order sequence exceeds the demonstration bound.";return false;}
    for(auto D:C.OrderSequence)if(!ValidDestination(C,D)) {Error="Invalid destination.";return false;}
    Settings=C;Ready=true;Reset();return true;
}
int Simulation::BinIndex(Destination D) const
{return Ready&&ValidDestination(Settings,D)?(D.Side*Settings.Columns+D.Column)*Settings.Levels+D.Level:-1;}
int Simulation::CartIndex(Destination D) const
{int I=BinIndex(D);return I<0?-1:Bins[size_t(I)].CartId;}
void Simulation::Reset()
{
    Playing=false;Rate=1.;AutoCollect=Settings.AutoCollect;Totals={};NextParcelId=1;NextOrder=0;
    ArrivalRemaining=0;CartElapsed=0;ActiveCart=-1;PreferredCart=0;ExchangePermit=true;PhaseElapsed.fill(0.);
    Infeed.clear();Bins.clear();Carts.clear();
    for(int I=0;I<CarrierCount;++I)
    {Carriers[I]={};Carriers[I].Distance01=double(I)/CarrierCount;Carriers[I].LiftHeightCm=Settings.LoadHeightCm;}
    if(!Ready)return;
    for(int Side=0;Side<2;++Side)for(int Col=0;Col<Settings.Columns;++Col)for(int Level=0;Level<Settings.Levels;++Level)
    {Bin B;B.Target={Side,Col,Level};B.Capacity=Settings.BinCapacity;Bins.push_back(B);}
    for(int Side=0;Side<2;++Side)for(int Col=0;Col<Settings.Columns;Col+=Settings.CartColumns)
    {
        Cart C;C.Index=int(Carts.size());C.Side=Side;C.FirstColumn=Col;
        C.ColumnCount=std::min(Settings.CartColumns,Settings.Columns-Col);C.Levels=Settings.Levels;
        C.Capacity=C.ColumnCount*C.Levels*Settings.BinCapacity;
        for(int K=Col;K<Col+C.ColumnCount;++K)for(int L=0;L<Settings.Levels;++L)
            Bins[size_t(BinIndex({Side,K,L}))].CartId=C.Index;
        Carts.push_back(C);
    }
    RefreshStatus();
}
bool Simulation::SetRate(double V) {if(V!=1.&&V!=2.&&V!=4.)return false;Rate=V;return true;}
void Simulation::SetAutoCollect(bool V) {AutoCollect=V;RefreshStatus();}
void Simulation::SetExchangePermit(bool V) {ExchangePermit=V;RefreshStatus();}
bool Simulation::ClearBin(Destination D) {return RequestCartExchange(CartIndex(D));}
bool Simulation::RequestCartExchange(int I)
{
    if(I<0||I>=int(Carts.size()))return false;
    auto& C=Carts[size_t(I)];
    if(C.State!=CartPhase::FullWaiting||C.Occupancy!=C.Capacity||C.Reserved!=0)return false;
    C.ExchangeRequested=true;RefreshStatus();return true;
}
bool Simulation::HasCarrierCargo() const
{for(const auto& C:Carriers)if(C.ParcelId)return true;return false;}
bool Simulation::ExchangePending() const
{
    if(ActiveCart>=0)return true;
    for(const auto& C:Carts)if(C.State==CartPhase::FullWaiting&&(AutoCollect||C.ExchangeRequested))return true;
    return false;
}
bool Simulation::FeedEnabled() const {return !ExchangePending();}
double Simulation::FeedFrontLimit() const
{
    // The parcel being scanned/inducted owns the end station until the transfer
    // finishes. Followers must wait one physical queue spacing behind it.
    for(const auto& C:Carriers)if(C.State==CarrierPhase::Scan||C.State==CarrierPhase::Induct)
        return 1.-1./double(Settings.InfeedCapacity+1);
    return 1.;
}
bool Simulation::FindDestination(Destination& Result) const
{
    auto Available=[this](Destination D)
    {
        int I=BinIndex(D);if(I<0)return false;
        const auto& B=Bins[size_t(I)];const auto& C=Carts[size_t(B.CartId)];
        return C.State==CartPhase::Receiving&&B.Occupancy+B.Reserved<B.Capacity;
    };
    if(!Settings.OrderSequence.empty())
    {Result=Settings.OrderSequence[size_t(NextOrder%Settings.OrderSequence.size())];return Available(Result);}
    // Visible whole-cart loading, not an assertion that real orders fill every bin.
    for(size_t N=0;N<Carts.size();++N)
    {
        const auto& C=Carts[(size_t(PreferredCart)+N)%Carts.size()];
        for(int Col=C.FirstColumn;Col<C.FirstColumn+C.ColumnCount;++Col)for(int L=0;L<C.Levels;++L)
            if(Available({C.Side,Col,L})) {Result={C.Side,Col,L};return true;}
    }
    return false;
}
bool Simulation::AtLoad(const Carrier& C) const
{return C.Distance01<=PositionTolerance||1.-C.Distance01<=PositionTolerance;}
double Simulation::TargetHeight(const Carrier& C) const
{
    return C.State==CarrierPhase::EmptyReturn||C.State==CarrierPhase::Scan||C.State==CarrierPhase::Induct
        ?Settings.LoadHeightCm:Settings.LevelHeightsCm[size_t(C.Target.Level)];
}
double Simulation::TargetDistance(const Carrier& C) const
{return Settings.DestinationDistances01[size_t(C.Target.Side*Settings.Columns+C.Target.Column)];}
double Simulation::CartDuration(CartPhase P) const
{
    switch(P)
    {
    case CartPhase::FullWaiting:return Settings.CollectSeconds;
    case CartPhase::Withdrawing:return Settings.CartWithdrawSeconds;
    case CartPhase::Outbound:return Settings.CartOutboundSeconds;
    case CartPhase::Handoff:return Settings.CartHandoffSeconds;
    case CartPhase::EmptyArriving:return Settings.CartEmptyArrivalSeconds;
    case CartPhase::Docking:return Settings.CartDockSeconds;
    default:return std::numeric_limits<double>::infinity();
    }
}
void Simulation::SettleEvents()
{
    bool Changed=true;
    while(Changed)
    {
        Changed=false;
        // Drain admitted parcels before stopping this machine for a cart exchange.
        if(ActiveCart<0&&ExchangePermit&&!HasCarrierCargo())
            for(auto& C:Carts)if(C.State==CartPhase::FullWaiting&&(AutoCollect||C.ExchangeRequested))
            {ActiveCart=C.Index;CartElapsed=0;C.Progress01=0;Changed=true;break;}
        if(ActiveCart>=0)
        {
            auto& C=Carts[size_t(ActiveCart)];
            if(CartElapsed>=CartDuration(C.State)-TimeTolerance&&(C.State!=CartPhase::FullWaiting||ExchangePermit))
            {
                CartElapsed=0;C.Progress01=0;Changed=true;
                switch(C.State)
                {
                case CartPhase::FullWaiting:C.State=CartPhase::Withdrawing;break;
                case CartPhase::Withdrawing:C.State=CartPhase::Outbound;break;
                case CartPhase::Outbound:C.State=CartPhase::Handoff;break;
                case CartPhase::Handoff:
                    C.LastOutboundParcelIds=C.ParcelIds;C.Collected+=uint64_t(C.Occupancy);
                    Totals.Collected+=uint64_t(C.Occupancy);C.ParcelIds.clear();C.Occupancy=0;
                    for(auto& B:Bins)if(B.CartId==C.Index)
                    {B.Collected+=uint64_t(B.Occupancy);B.Occupancy=0;B.ParcelIds.clear();}
                    ++C.Generation;C.State=CartPhase::EmptyArriving;break;
                case CartPhase::EmptyArriving:C.State=CartPhase::Docking;break;
                case CartPhase::Docking:
                    C.State=CartPhase::Receiving;C.ExchangeRequested=false;++Totals.ExchangedCarts;
                    PreferredCart=(C.Index+1)%int(Carts.size());ActiveCart=-1;break;
                default:break;
                }
            }
        }
        if(FeedEnabled()&&ArrivalRemaining<=TimeTolerance&&Infeed.size()<size_t(Settings.InfeedCapacity))
        {
            const double Gap=1./double(Settings.InfeedCapacity+1);
            if(Infeed.empty()||Infeed.back().Progress01>=Gap-PositionTolerance)
            {Infeed.push_back({NextParcelId++,0});++Totals.Spawned;++Totals.InfeedReceived;ArrivalRemaining=Settings.InfeedSpacingSeconds;Changed=true;}
        }
        if(ActiveCart>=0)continue;
        for(int I=0;I<CarrierCount;++I)
        {
            auto& C=Carriers[I];
            switch(C.State)
            {
            case CarrierPhase::EmptyReturn:
                if(AtLoad(C)&&std::abs(C.LiftHeightCm-Settings.LoadHeightCm)<=HeightTolerance&&FeedEnabled()
                   &&!Infeed.empty()&&Infeed.front().Progress01>=1.-PositionTolerance)
                {
                    Destination D;if(!FindDestination(D))break;
                    auto& B=Bins[size_t(BinIndex(D))];auto& Cart=Carts[size_t(B.CartId)];
                    C.LiftHeightCm=Settings.LoadHeightCm;C.State=CarrierPhase::Scan;C.Target=D;
                    C.ParcelId=Infeed.front().ParcelId;Infeed.erase(Infeed.begin());
                    C.TargetCartIndex=Cart.Index;C.TargetCartGeneration=Cart.Generation;
                    C.ScanProgress=0;C.InductProgress=0;C.UnloadProgress=0;PhaseElapsed[I]=0;
                    ++B.Reserved;++Cart.Reserved;++NextOrder;PreferredCart=Cart.Index;Changed=true;
                }
                break;
            case CarrierPhase::Scan:
                if(PhaseElapsed[I]>=Settings.ScanSeconds-TimeTolerance)
                {C.ScanProgress=1;C.State=CarrierPhase::Induct;PhaseElapsed[I]=0;Changed=true;}
                break;
            case CarrierPhase::Induct:
                if(PhaseElapsed[I]>=Settings.InductSeconds-TimeTolerance)
                {C.InductProgress=1;C.State=CarrierPhase::LoadedTravel;PhaseElapsed[I]=0;Changed=true;}
                break;
            case CarrierPhase::LoadedTravel:
                if(std::abs(C.Distance01-TargetDistance(C))<=PositionTolerance)
                {C.State=CarrierPhase::Lift;PhaseElapsed[I]=0;Changed=true;}
                break;
            case CarrierPhase::Lift:
                if(std::abs(C.LiftHeightCm-TargetHeight(C))<=HeightTolerance)
                {
                    const auto& Cart=Carts[size_t(C.TargetCartIndex)];
                    if(Cart.State==CartPhase::Receiving&&Cart.Generation==C.TargetCartGeneration)
                    {C.LiftHeightCm=TargetHeight(C);C.State=CarrierPhase::Unload;PhaseElapsed[I]=0;Changed=true;}
                }
                break;
            case CarrierPhase::Unload:
                if(PhaseElapsed[I]>=Settings.UnloadSeconds-TimeTolerance)
                {
                    auto& B=Bins[size_t(BinIndex(C.Target))];auto& Cart=Carts[size_t(C.TargetCartIndex)];
                    --B.Reserved;--Cart.Reserved;++B.Occupancy;++B.Delivered;++Cart.Occupancy;++Totals.Completed;
                    B.ParcelIds.push_back(C.ParcelId);Cart.ParcelIds.push_back(C.ParcelId);
                    if(Cart.Occupancy==Cart.Capacity) {Cart.State=CartPhase::FullWaiting;Cart.Progress01=0;}
                    C.ParcelId=0;C.State=CarrierPhase::EmptyReturn;C.TargetCartIndex=-1;
                    C.TargetCartGeneration=0;C.ScanProgress=0;C.InductProgress=0;C.UnloadProgress=0;
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
    Totals.Active=0;Totals.Queued=int(Infeed.size());Totals.Reason=BlockReason::None;
    Totals.WaitingForCart=ExchangePending();
    for(const auto& C:Carts)Totals.WaitingForCart|=C.State==CartPhase::FullWaiting;
    bool Scan=false,Induct=false,Lift=false,Unload=false,Wait=false,Full=false;Destination Candidate;
    for(const auto& C:Carriers)
    {
        if(C.ParcelId)++Totals.Active;
        Scan|=C.State==CarrierPhase::Scan;Induct|=C.State==CarrierPhase::Induct;
        Lift|=C.State==CarrierPhase::Lift;Unload|=C.State==CarrierPhase::Unload;
        if(C.State==CarrierPhase::EmptyReturn&&AtLoad(C))
        {
            Lift|=std::abs(C.LiftHeightCm-Settings.LoadHeightCm)>HeightTolerance;
            if(FeedEnabled())
            {
                Wait|=Infeed.empty()||Infeed.front().Progress01<1.-PositionTolerance;
                Full|=!FindDestination(Candidate);
            }
        }
    }
    if(ActiveCart>=0)Totals.Reason=BlockReason::CartExchange;
    else if(Unload)Totals.Reason=BlockReason::Unloading;
    else if(Lift)Totals.Reason=BlockReason::Lifting;
    else if(Scan)Totals.Reason=BlockReason::Scanning;
    else if(Induct)Totals.Reason=BlockReason::Inducting;
    else if((Full||ExchangePending())&&!HasCarrierCargo())Totals.Reason=BlockReason::FullBin;
    else if(Wait&&!HasCarrierCargo())Totals.Reason=BlockReason::WaitingInfeed;
    Totals.ChainStopped=Totals.Reason!=BlockReason::None;
}
double Simulation::NextEventSeconds(bool MoveChain) const
{
    double Next=std::numeric_limits<double>::infinity();
    if(ActiveCart>=0)
    {
        if(Carts[size_t(ActiveCart)].State==CartPhase::FullWaiting&&!ExchangePermit)return Next;
        return std::max(TimeTolerance,CartDuration(Carts[size_t(ActiveCart)].State)-CartElapsed);
    }
    const double Velocity=Settings.ChainSpeedCmS/Settings.LoopLengthCm;
    for(int I=0;I<CarrierCount;++I)
    {
        const auto& C=Carriers[I];
        if(MoveChain&&(C.State==CarrierPhase::EmptyReturn||C.State==CarrierPhase::LoadedTravel))
        {
            double D=C.State==CarrierPhase::EmptyReturn?ForwardDistance(C.Distance01,0.):ForwardDistance(C.Distance01,TargetDistance(C));
            if(D<=PositionTolerance)D=1.;
            Next=std::min(Next,D/Velocity);
        }
        double H=std::abs(TargetHeight(C)-C.LiftHeightCm);if(H>HeightTolerance)Next=std::min(Next,H/Settings.LiftSpeedCmS);
        if(C.State==CarrierPhase::Scan)Next=std::min(Next,Settings.ScanSeconds-PhaseElapsed[I]);
        if(C.State==CarrierPhase::Induct)Next=std::min(Next,Settings.InductSeconds-PhaseElapsed[I]);
        if(C.State==CarrierPhase::Unload)Next=std::min(Next,Settings.UnloadSeconds-PhaseElapsed[I]);
    }
    if(FeedEnabled())
    {
        const double Gap=1./double(Settings.InfeedCapacity+1);
        for(size_t I=0;I<Infeed.size();++I)
        {
            double D=FeedFrontLimit()-double(I)*Gap-Infeed[I].Progress01;
            if(D>PositionTolerance)Next=std::min(Next,D*Settings.InfeedTravelSeconds);
        }
        if(Infeed.size()<size_t(Settings.InfeedCapacity))
        {
            if(ArrivalRemaining>TimeTolerance)Next=std::min(Next,ArrivalRemaining);
            else if(!Infeed.empty()&&Infeed.back().Progress01<Gap-PositionTolerance)
                Next=std::min(Next,(Gap-Infeed.back().Progress01)*Settings.InfeedTravelSeconds);
        }
    }
    return Next;
}
void Simulation::Integrate(double Seconds,bool MoveChain)
{
    Totals.SimTime+=Seconds;
    if(MoveChain)Totals.ChainPhase01=Wrap(Totals.ChainPhase01+Settings.ChainSpeedCmS*Seconds/Settings.LoopLengthCm);
    else Totals.BlockedSeconds+=Seconds;
    if(ActiveCart>=0)
    {
        auto& C=Carts[size_t(ActiveCart)];
        if(C.State!=CartPhase::FullWaiting||ExchangePermit){CartElapsed+=Seconds;C.Progress01=std::min(1.,CartElapsed/CartDuration(C.State));}
        return;
    }
    for(int I=0;I<CarrierCount;++I)
    {
        auto& C=Carriers[I];C.Distance01=Wrap(Totals.ChainPhase01+double(I)/CarrierCount);
        double D=TargetHeight(C)-C.LiftHeightCm,M=Settings.LiftSpeedCmS*Seconds;
        C.LiftHeightCm+=std::clamp(D,-M,M);
        if(C.State==CarrierPhase::Scan) {PhaseElapsed[I]+=Seconds;C.ScanProgress=std::min(1.,PhaseElapsed[I]/Settings.ScanSeconds);}
        if(C.State==CarrierPhase::Induct) {PhaseElapsed[I]+=Seconds;C.InductProgress=std::min(1.,PhaseElapsed[I]/Settings.InductSeconds);}
        if(C.State==CarrierPhase::Unload) {PhaseElapsed[I]+=Seconds;C.UnloadProgress=std::min(1.,PhaseElapsed[I]/Settings.UnloadSeconds);}
    }
    if(FeedEnabled())
    {
        ArrivalRemaining=std::max(0.,ArrivalRemaining-Seconds);const double Gap=1./double(Settings.InfeedCapacity+1);
        for(size_t I=0;I<Infeed.size();++I)
            Infeed[I].Progress01=std::min(FeedFrontLimit()-double(I)*Gap,Infeed[I].Progress01+Seconds/Settings.InfeedTravelSeconds);
    }
}
bool Simulation::Advance(double WallDeltaSeconds)
{
    if(!Ready||!std::isfinite(WallDeltaSeconds)||WallDeltaSeconds<0||WallDeltaSeconds>86400./Rate)return false;
    if(!Playing||WallDeltaSeconds==0)return true;
    double Remaining=WallDeltaSeconds*Rate;SettleEvents();
    while(Remaining>0.)
    {
        bool Move=!Totals.ChainStopped;double Step=std::min(Remaining,NextEventSeconds(Move));
        if(!(Step>0.)||!std::isfinite(Step))return false;
        Integrate(Step,Move);Remaining=std::max(0.,Remaining-Step);SettleEvents();
    }
    return true;
}
}
