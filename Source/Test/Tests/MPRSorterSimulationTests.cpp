#if WITH_DEV_AUTOMATION_TESTS || defined(MPR_SORTER_STANDALONE)
#include "../MPRSorterSimulation.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#ifdef MPR_SORTER_STANDALONE
#include <iostream>
using FString=std::string;
#define TEXT(X) X
static int MPRFailures=0;
struct MPRTestBase { void TestTrue(const char* Message,bool Value) {if(!Value){++MPRFailures;std::cerr<<"FAIL: "<<Message<<'\n';}} };
#define IMPLEMENT_SIMPLE_AUTOMATION_TEST(Type,Name,Flags) struct Type:MPRTestBase { bool RunTest(const FString&); };
#else
#include "GHSAutomationTestFlags.h"
#endif
namespace
{
#ifndef MPR_SORTER_STANDALONE
constexpr auto MPRFlags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
#endif
MPRSorter::Config MPRFixture()
{
    MPRSorter::Config C;C.Columns=3;C.Levels=4;C.BinCapacity=2;
    C.LoopLengthCm=1400;C.ChainSpeedCmS=140;C.LoadHeightCm=103.5;
    C.LevelHeightsCm={42,86.5,131,175.5};C.DestinationDistances01={.15,.25,.35,.65,.75,.85};
    C.ScanSeconds=.35;C.UnloadSeconds=.8;C.LiftSpeedCmS=55;
    return C;
}
bool Near(double A,double B,double E=1.e-6) {return std::abs(A-B)<=E;}
bool MPRSame(const MPRSorter::Simulation& A,const MPRSorter::Simulation& B)
{
    const auto& X=A.GetStats();const auto& Y=B.GetStats();
    if(X.Spawned!=Y.Spawned||X.Completed!=Y.Completed||X.Collected!=Y.Collected||X.Active!=Y.Active
       ||X.Queued!=Y.Queued||X.ExchangedCarts!=Y.ExchangedCarts||X.Reason!=Y.Reason||X.ChainStopped!=Y.ChainStopped
       ||X.WaitingForCart!=Y.WaitingForCart||!Near(X.SimTime,Y.SimTime)||!Near(X.ChainPhase01,Y.ChainPhase01,1.e-8))return false;
    for(int I=0;I<MPRSorter::CarrierCount;++I)
    {
        const auto& P=A.GetCarriers()[I];const auto& Q=B.GetCarriers()[I];
        if(P.State!=Q.State||P.ParcelId!=Q.ParcelId||!(P.Target==Q.Target)||P.TargetCartIndex!=Q.TargetCartIndex
           ||P.TargetCartGeneration!=Q.TargetCartGeneration||!Near(P.Distance01,Q.Distance01,1.e-8)
           ||!Near(P.LiftHeightCm,Q.LiftHeightCm)||!Near(P.ScanProgress,Q.ScanProgress)
           ||!Near(P.InductProgress,Q.InductProgress)||!Near(P.UnloadProgress,Q.UnloadProgress))return false;
    }
    const auto& AQ=A.GetInfeedQueue();const auto& BQ=B.GetInfeedQueue();if(AQ.size()!=BQ.size())return false;
    for(size_t I=0;I<AQ.size();++I)if(AQ[I].ParcelId!=BQ[I].ParcelId||!Near(AQ[I].Progress01,BQ[I].Progress01))return false;
    const auto& AB=A.GetBins();const auto& BB=B.GetBins();if(AB.size()!=BB.size())return false;
    for(size_t I=0;I<AB.size();++I)
        if(AB[I].Occupancy!=BB[I].Occupancy||AB[I].Reserved!=BB[I].Reserved||AB[I].Delivered!=BB[I].Delivered
           ||AB[I].Collected!=BB[I].Collected||AB[I].ParcelIds!=BB[I].ParcelIds)return false;
    const auto& AC=A.GetCarts();const auto& BC=B.GetCarts();if(AC.size()!=BC.size())return false;
    for(size_t I=0;I<AC.size();++I)
        if(AC[I].State!=BC[I].State||AC[I].Occupancy!=BC[I].Occupancy||AC[I].Reserved!=BC[I].Reserved
           ||AC[I].Generation!=BC[I].Generation||AC[I].ParcelIds!=BC[I].ParcelIds||AC[I].Collected!=BC[I].Collected
           ||AC[I].LastOutboundParcelIds!=BC[I].LastOutboundParcelIds||!Near(AC[I].Progress01,BC[I].Progress01))return false;
    return true;
}
bool MPRConserved(const MPRSorter::Simulation& S)
{
    const auto& T=S.GetStats();std::set<uint64_t> Ids;uint64_t Occupancy=0,Delivered=0,Collected=0;
    int Reserved=0,CarrierParcels=0;
    const auto& Q=S.GetInfeedQueue();if(Q.size()>size_t(S.GetConfig().InfeedCapacity))return false;
    for(size_t I=0;I<Q.size();++I)
    {
        if(!Q[I].ParcelId||!Ids.insert(Q[I].ParcelId).second||!std::isfinite(Q[I].Progress01)||Q[I].Progress01<0||Q[I].Progress01>1)return false;
        if(I&&Q[I-1].Progress01-Q[I].Progress01<1./double(S.GetConfig().InfeedCapacity+1)-1.e-8)return false;
    }
    for(const auto& C:S.GetCarriers())
    {
        if(C.ParcelId)
        {
            if(!Ids.insert(C.ParcelId).second||C.TargetCartIndex<0)return false;
            ++CarrierParcels;const auto& Cart=S.GetCarts()[size_t(C.TargetCartIndex)];
            if(Cart.State!=MPRSorter::CartPhase::Receiving||Cart.Generation!=C.TargetCartGeneration)return false;
            if((C.State==MPRSorter::CarrierPhase::Scan||C.State==MPRSorter::CarrierPhase::Induct)&&!Q.empty()
               &&Q.front().Progress01>1.-1./double(S.GetConfig().InfeedCapacity+1)+1.e-8)return false;
        }
        if(!std::isfinite(C.Distance01)||C.Distance01<0||C.Distance01>=1)return false;
    }
    for(const auto& B:S.GetBins())
    {
        if(B.Occupancy<0||B.Reserved<0||B.Occupancy+B.Reserved>B.Capacity||B.ParcelIds.size()!=size_t(B.Occupancy))return false;
        for(uint64_t Id:B.ParcelIds)if(!Ids.insert(Id).second)return false;
        Occupancy+=B.Occupancy;Reserved+=B.Reserved;Delivered+=B.Delivered;Collected+=B.Collected;
    }
    for(const auto& C:S.GetCarts())
    {
        int O=0,R=0;std::set<uint64_t> Manifest;
        for(const auto& B:S.GetBins())if(B.CartId==C.Index){O+=B.Occupancy;R+=B.Reserved;Manifest.insert(B.ParcelIds.begin(),B.ParcelIds.end());}
        if(O!=C.Occupancy||R!=C.Reserved||Manifest!=std::set<uint64_t>(C.ParcelIds.begin(),C.ParcelIds.end())
           ||C.ParcelIds.size()!=size_t(O)||C.Occupancy+C.Reserved>C.Capacity)return false;
        if(C.State!=MPRSorter::CartPhase::Receiving&&C.Reserved)return false;
    }
    return T.Spawned==Ids.size()+T.Collected&&T.Completed==Occupancy+T.Collected&&T.Completed==Delivered
        &&T.Collected==Collected&&Reserved==CarrierParcels&&T.Active==CarrierParcels&&T.Queued==int(Q.size());
}
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterConfiguration,"MPR.Sorter.Configuration",MPRFlags)
bool FMPRSorterConfiguration::RunTest(const FString&)
{
    MPRSorter::Simulation S;std::string Error;auto C=MPRFixture();
    TestTrue(TEXT("explicit profile accepted paused"),S.Initialize(C,Error)&&!S.IsPlaying());
    auto Bad=C;Bad.DestinationDistances01.pop_back();TestTrue(TEXT("incomplete stations rejected"),!S.Initialize(Bad,Error)&&!Error.empty());
    Bad=C;Bad.LevelHeightsCm[0]=std::numeric_limits<double>::quiet_NaN();TestTrue(TEXT("nonfinite geometry rejected"),!S.Initialize(Bad,Error));
    Bad=C;Bad.CartWithdrawSeconds=std::numeric_limits<double>::infinity();TestTrue(TEXT("nonfinite exchange duration rejected"),!S.Initialize(Bad,Error));
    Bad=C;Bad.CartHandoffSeconds=std::numeric_limits<double>::quiet_NaN();TestTrue(TEXT("nonfinite handoff duration rejected"),!S.Initialize(Bad,Error));
    Bad=C;Bad.InfeedCapacity=0;TestTrue(TEXT("unbounded or absent queue rejected"),!S.Initialize(Bad,Error));
    Bad=C;Bad.CartColumns=0;TestTrue(TEXT("zero cart width rejected"),!S.Initialize(Bad,Error));
    Bad=C;Bad.OrderSequence={{2,0,0}};TestTrue(TEXT("invalid order rejected"),!S.Initialize(Bad,Error));
    auto Before=S;Bad=C;Bad.InductSeconds=-1;TestTrue(TEXT("invalid initialization preserves ready state"),!S.Initialize(Bad,Error)&&MPRSame(S,Before));
    C.Columns=8;C.CartColumns=3;C.DestinationDistances01.clear();for(int I=0;I<16;++I)C.DestinationDistances01.push_back(double(I+1)/17.);
    TestTrue(TEXT("scene tail groups accepted"),S.Initialize(C,Error)&&S.GetCarts().size()==6&&S.GetCarts()[2].ColumnCount==2);
    C.CartColumns=4;TestTrue(TEXT("CAD-specific 4-column carts accepted"),S.Initialize(C,Error)&&S.GetCarts().size()==4);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterFrameEquivalence,"MPR.Sorter.DeterministicFramePartition",MPRFlags)
bool FMPRSorterFrameEquivalence::RunTest(const FString&)
{
    MPRSorter::Simulation A,B,C;std::string E;A.Initialize(MPRFixture(),E);B.Initialize(MPRFixture(),E);C.Initialize(MPRFixture(),E);
    A.SetPlaying(true);B.SetPlaying(true);C.SetPlaying(true);
    TestTrue(TEXT("large step covers complete exchanges"),A.Advance(1800.125)&&A.GetStats().ExchangedCarts>2);
    bool Small=true;for(int I=0;I<18000;++I)Small&=B.Advance(.1);Small&=B.Advance(.125);
    C.Advance(233.125);C.Advance(1567);
    TestTrue(TEXT("frame partition preserves queue/carrier/cart events"),Small&&MPRSame(A,B)&&MPRSame(A,C));
    TestTrue(TEXT("all parcels and reservations conserved"),MPRConserved(A)&&MPRConserved(B)&&MPRConserved(C));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterWholeCart,"MPR.Sorter.FullCartExchangeLifecycle",MPRFlags)
bool FMPRSorterWholeCart::RunTest(const FString&)
{
    auto C=MPRFixture();C.BinCapacity=1;C.AutoCollect=false;
    MPRSorter::Simulation S;std::string E;S.Initialize(C,E);S.SetPlaying(true);
    TestTrue(TEXT("empty cart cannot be removed"),!S.RequestCartExchange(0)&&!S.ClearBin({0,0,0}));
    bool Full=false;
    for(int I=0;I<10000&&!Full;++I){S.Advance(.1);Full=S.GetCarts()[0].State==MPRSorter::CartPhase::FullWaiting;}
    TestTrue(TEXT("all twelve bins filled before the cart becomes full"),Full&&S.GetCarts()[0].Occupancy==12&&S.GetStats().Collected==0);
    S.Advance(30);TestTrue(TEXT("auto-off holds complete loaded cart"),S.GetCarts()[0].State==MPRSorter::CartPhase::FullWaiting&&S.GetCarts()[0].Occupancy==12);
    const auto Manifest=S.GetCarts()[0].ParcelIds;
    TestTrue(TEXT("legacy ClearBin requests entire cart only"),S.ClearBin({0,0,0})&&S.GetCarts()[0].ParcelIds==Manifest);
    bool SawWithdraw=false,SawOutbound=false,SawHandoff=false,SawEmpty=false,SawDock=false,Preserved=true,Frozen=true,Conserved=true;
    bool HandoffDelay=true,HandoffPause=true,AbsentBlocked=true;
    double LastPhase=S.GetStats().ChainPhase01;bool WasChanging=false;
    for(int I=0;I<5000&&S.GetStats().ExchangedCarts==0;++I)
    {
        S.Advance(.01);const auto& Cart=S.GetCarts()[0];const auto& T=S.GetStats();
        SawWithdraw|=Cart.State==MPRSorter::CartPhase::Withdrawing;SawOutbound|=Cart.State==MPRSorter::CartPhase::Outbound;
        SawEmpty|=Cart.State==MPRSorter::CartPhase::EmptyArriving;SawDock|=Cart.State==MPRSorter::CartPhase::Docking;
        if(Cart.State==MPRSorter::CartPhase::Withdrawing||Cart.State==MPRSorter::CartPhase::Outbound||Cart.State==MPRSorter::CartPhase::Handoff)
            Preserved&=Cart.ParcelIds==Manifest&&Cart.Occupancy==12&&Cart.Collected==0&&Cart.Generation==1;
        if(Cart.State==MPRSorter::CartPhase::EmptyArriving||Cart.State==MPRSorter::CartPhase::Docking)
            Preserved&=Cart.Occupancy==0&&Cart.LastOutboundParcelIds==Manifest&&Cart.Collected==12&&Cart.Generation==2;
        if(Cart.State==MPRSorter::CartPhase::Handoff&&!SawHandoff)
        {
            SawHandoff=true;
            auto Paused=S;Paused.SetPlaying(false);const auto Snapshot=Paused;Paused.Advance(10);
            HandoffPause&=MPRSame(Paused,Snapshot);
            auto Boundary=S;const double Remaining=(1.-Cart.Progress01)*C.CartHandoffSeconds;
            Boundary.Advance(Remaining-.0001);
            HandoffDelay&=Boundary.GetCarts()[0].State==MPRSorter::CartPhase::Handoff
                &&Boundary.GetCarts()[0].ParcelIds==Manifest&&Boundary.GetCarts()[0].Collected==0;
            Boundary.Advance(.0002);
            HandoffDelay&=Boundary.GetCarts()[0].State==MPRSorter::CartPhase::EmptyArriving
                &&Boundary.GetCarts()[0].Generation==2&&Boundary.GetCarts()[0].Occupancy==0
                &&Boundary.GetCarts()[0].LastOutboundParcelIds==Manifest&&MPRConserved(Boundary);
        }
        if(Cart.State==MPRSorter::CartPhase::Handoff||Cart.State==MPRSorter::CartPhase::EmptyArriving||Cart.State==MPRSorter::CartPhase::Docking)
            AbsentBlocked&=T.Active==0&&Cart.Reserved==0&&T.ChainStopped&&!S.RequestCartExchange(0);
        bool Changing=T.Reason==MPRSorter::BlockReason::CartExchange;
        if(Changing&&WasChanging)Frozen&=Near(LastPhase,T.ChainPhase01,1.e-10)&&T.Active==0;
        WasChanging=Changing;LastPhase=T.ChainPhase01;Conserved&=MPRConserved(S);
    }
    TestTrue(TEXT("full staged cart hands off before a distinct empty cart docks"),SawWithdraw&&SawOutbound&&SawHandoff&&SawEmpty&&SawDock&&S.GetCarts()[0].Generation==2&&S.GetStats().ExchangedCarts==1);
    TestTrue(TEXT("load remains on the old cart until handoff completion"),Preserved);
    TestTrue(TEXT("handoff has a real bounded delay before replacement generation starts"),HandoffDelay&&SawHandoff);
    TestTrue(TEXT("handoff pause preserves the old manifest and clock"),HandoffPause&&SawHandoff);
    TestTrue(TEXT("an absent cart cannot be reserved or requested again"),AbsentBlocked);
    TestTrue(TEXT("local chain stops only after admitted parcels finish"),Frozen);
    TestTrue(TEXT("entire cart exchange conserves every parcel"),Conserved);
    S.SetAutoCollect(true);S.Advance(1000);TestTrue(TEXT("auto-on resumes repeated complete cart exchanges"),S.GetStats().ExchangedCarts>2&&MPRConserved(S));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterInfeed,"MPR.Sorter.InfeedHandoffAndReservations",MPRFlags)
bool FMPRSorterInfeed::RunTest(const FString&)
{
    MPRSorter::Simulation S;std::string E;S.Initialize(MPRFixture(),E);S.SetPlaying(true);
    bool Good=true,SawScan=false,SawInduct=false,SawUnload=false,FirstFeedSeen=false;uint64_t FirstId=0;
    for(int I=0;I<12000;++I)
    {
        Good&=S.Advance(.05)&&MPRConserved(S);
        for(const auto& P:S.GetInfeedQueue())if(!FirstId){FirstId=P.ParcelId;FirstFeedSeen=true;}
        for(const auto& P:S.GetCarriers())
        {
            SawScan|=P.State==MPRSorter::CarrierPhase::Scan&&P.ParcelId==FirstId;
            SawInduct|=P.State==MPRSorter::CarrierPhase::Induct&&P.ParcelId==FirstId&&P.InductProgress>0&&P.InductProgress<1;
            SawUnload|=P.State==MPRSorter::CarrierPhase::Unload&&P.ParcelId==FirstId;
            if(P.State==MPRSorter::CarrierPhase::Unload)
                Good&=Near(P.LiftHeightCm,S.GetConfig().LevelHeightsCm[size_t(P.Target.Level)]);
        }
        const auto& Cars=S.GetCarriers();for(int J=1;J<MPRSorter::CarrierCount;++J)
            Good&=Near(std::fmod(Cars[J].Distance01-Cars[0].Distance01+1.,1.),J*.25,1.e-8);
    }
    TestTrue(TEXT("the original conveyor parcel reaches scan induction and unloading"),FirstFeedSeen&&SawScan&&SawInduct&&SawUnload);
    TestTrue(TEXT("bounded separated feed, unique ownership, reservations and chain spacing hold"),Good);
    auto C=MPRFixture();C.OrderSequence={{0,0,0}};C.BinCapacity=1;C.AutoCollect=false;
    S.Initialize(C,E);S.SetPlaying(true);S.Advance(300);
    TestTrue(TEXT("a single full bin does not claim a full cart or erase contents"),S.GetStats().Completed==1&&!S.ClearBin({0,0,0})&&S.GetStats().Collected==0&&MPRConserved(S));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterPauseReset,"MPR.Sorter.PauseRateResetAndInvalidInput",MPRFlags)
bool FMPRSorterPauseReset::RunTest(const FString&)
{
    MPRSorter::Simulation A,B;std::string E;A.Initialize(MPRFixture(),E);B.Initialize(MPRFixture(),E);A.SetPlaying(true);A.Advance(70);
    A.SetPlaying(false);auto Snapshot=A;A.Advance(100);TestTrue(TEXT("pause freezes queue carrier and cart state"),MPRSame(A,Snapshot));
    A.SetPlaying(true);A.SetRate(4);A.Advance(100);B.SetPlaying(true);B.Advance(470);
    TestTrue(TEXT("4x affects only elapsed simulation time"),MPRSame(A,B));
    Snapshot=A;TestTrue(TEXT("invalid deltas rejected without mutation"),!A.Advance(-1)&&!A.Advance(std::numeric_limits<double>::quiet_NaN())&&!A.Advance(1.e30)&&MPRSame(A,Snapshot));
    TestTrue(TEXT("invalid rates rejected"),!A.SetRate(3)&&!A.SetRate(std::numeric_limits<double>::infinity()));
    A.Reset();B.Reset();TestTrue(TEXT("reset clears all epochs counters and motion and pauses at 1x"),!A.IsPlaying()&&A.GetRate()==1&&MPRSame(A,B)&&A.GetStats().Spawned==0);
    A.SetPlaying(true);A.SetRate(2);A.Advance(150);B.SetPlaying(true);B.Advance(300);TestTrue(TEXT("2x after reset remains deterministic"),MPRSame(A,B));
    bool MovingCart=false;
    for(int I=0;I<10000&&!MovingCart;++I)
    {
        A.Advance(.1);for(const auto& Cart:A.GetCarts())MovingCart|=Cart.State==MPRSorter::CartPhase::Withdrawing&&Cart.Progress01>.1;
    }
    A.SetPlaying(false);Snapshot=A;A.Advance(100);
    TestTrue(TEXT("pause also freezes a partially withdrawn loaded cart"),MovingCart&&MPRSame(A,Snapshot));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterSceneProfiles,"MPR.Sorter.CADCartProfiles",MPRFlags)
bool FMPRSorterSceneProfiles::RunTest(const FString&)
{
    for(const auto& Shape:std::vector<std::array<int,3>>{{5,1,5},{8,4,4},{15,4,5}})
    {
        auto C=MPRFixture();C.Columns=Shape[0];C.Levels=Shape[1];C.CartColumns=Shape[2];
        C.LevelHeightsCm.resize(size_t(C.Levels));C.DestinationDistances01.clear();
        for(int I=0;I<2*C.Columns;++I)C.DestinationDistances01.push_back(double(I+1)/double(2*C.Columns+1));
        MPRSorter::Simulation A,B;std::string E;bool Good=A.Initialize(C,E)&&B.Initialize(C,E);
        A.SetPlaying(true);B.SetPlaying(true);Good&=A.Advance(1200);
        for(int I=0;I<2400;++I)Good&=B.Advance(.5)&&MPRConserved(B);
        Good&=A.GetStats().ExchangedCarts>0&&MPRConserved(A)&&MPRSame(A,B);
        TestTrue(TEXT("one-level, four-column and long multilevel CAD cart groups complete whole exchanges"),Good);
    }
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterExchangePermit,"MPR.Sorter.SharedAislePermit",MPRFlags)
bool FMPRSorterExchangePermit::RunTest(const FString&)
{
    auto C=MPRFixture();C.BinCapacity=1;MPRSorter::Simulation S;std::string E;
    S.Initialize(C,E);S.SetExchangePermit(false);S.SetPlaying(true);S.Advance(600);
    TestTrue(TEXT("permit holds the complete cart while preserving auto preference"),S.IsAutoCollectEnabled()&&S.GetStats().Collected==0
        &&S.GetCarts()[0].State==MPRSorter::CartPhase::FullWaiting&&S.GetStats().Active==0&&MPRConserved(S));
    const auto Full=S.GetCarts()[0].ParcelIds;
    S.SetExchangePermit(true);S.Advance(C.CollectSeconds*.5);const double P=S.GetCarts()[0].Progress01;
    S.SetExchangePermit(false);S.Advance(100);
    TestTrue(TEXT("revoked permission freezes full waiting before any withdrawal"),S.GetCarts()[0].State==MPRSorter::CartPhase::FullWaiting
        &&Near(S.GetCarts()[0].Progress01,P)&&S.GetCarts()[0].ParcelIds==Full);
    S.SetExchangePermit(true);S.Advance(C.CollectSeconds*.5+C.CartWithdrawSeconds+C.CartOutboundSeconds+C.CartHandoffSeconds+C.CartEmptyArrivalSeconds+C.CartDockSeconds+.001);
    TestTrue(TEXT("grant completes one whole cart and retains conservation"),S.GetCarts()[0].Generation==2&&S.GetCarts()[0].Collected==12&&MPRConserved(S));
    return true;
}
#ifdef MPR_SORTER_STANDALONE
int main()
{
    FMPRSorterConfiguration().RunTest("");FMPRSorterFrameEquivalence().RunTest("");FMPRSorterWholeCart().RunTest("");
    FMPRSorterInfeed().RunTest("");FMPRSorterPauseReset().RunTest("");FMPRSorterSceneProfiles().RunTest("");FMPRSorterExchangePermit().RunTest("");
    auto C=MPRFixture();C.BinCapacity=3;C.ChainSpeedCmS=40;
    MPRSorter::Simulation S;std::string E;S.Initialize(C,E);S.SetPlaying(true);
    double Full=-1,Out=-1,Docked=-1;
    for(int I=0;I<200000&&Docked<0;++I){S.Advance(.01);const auto& P=S.GetCarts()[0];if(Full<0&&P.State==MPRSorter::CartPhase::FullWaiting)Full=S.GetStats().SimTime;if(Out<0&&P.Collected>0)Out=S.GetStats().SimTime;if(S.GetStats().ExchangedCarts>0)Docked=S.GetStats().SimTime;}
    std::cout<<"36-piece cart example: full="<<Full<<"s collected="<<Out<<"s replacement docked="<<Docked<<"s\n";
    std::cout<<"MPR core tests: "<<MPRFailures<<" failures\n";return MPRFailures?1:0;
}
#endif
#endif
