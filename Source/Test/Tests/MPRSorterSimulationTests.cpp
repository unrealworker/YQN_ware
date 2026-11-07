#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulation.h"
#include "GHSAutomationTestFlags.h"
#include <cmath>
#include <limits>
#include <set>

namespace
{
constexpr auto MPRFlags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
MPRSorter::Config MPRFixture()
{
    MPRSorter::Config C;
    C.Columns=3;C.Levels=4;C.BinCapacity=2;
    C.LoopLengthCm=1400;C.ChainSpeedCmS=140;
    C.LoadHeightCm=103.5;C.LevelHeightsCm={42,86.5,131,175.5};
    C.DestinationDistances01={.15,.25,.35,.65,.75,.85};
    C.ScanSeconds=.35;C.UnloadSeconds=.8;C.LiftSpeedCmS=55;
    return C;
}
bool MPRSame(const MPRSorter::Simulation& A,const MPRSorter::Simulation& B)
{
    const auto& X=A.GetStats();const auto& Y=B.GetStats();
    if(X.Spawned!=Y.Spawned||X.Completed!=Y.Completed||X.Collected!=Y.Collected||X.Active!=Y.Active
       ||X.ChainStopped!=Y.ChainStopped||X.Reason!=Y.Reason||std::abs(X.SimTime-Y.SimTime)>1.e-6)return false;
    for(int I=0;I<MPRSorter::CarrierCount;++I)
    {
        const auto& P=A.GetCarriers()[I];const auto& Q=B.GetCarriers()[I];
        if(P.State!=Q.State||P.ParcelId!=Q.ParcelId||!(P.Target==Q.Target)
           ||std::abs(P.Distance01-Q.Distance01)>1.e-8||std::abs(P.LiftHeightCm-Q.LiftHeightCm)>1.e-6
           ||std::abs(P.ScanProgress-Q.ScanProgress)>1.e-7||std::abs(P.UnloadProgress-Q.UnloadProgress)>1.e-7)return false;
    }
    const auto& AB=A.GetBins();const auto& BB=B.GetBins();if(AB.size()!=BB.size())return false;
    for(size_t I=0;I<AB.size();++I)
        if(AB[I].Occupancy!=BB[I].Occupancy||AB[I].Reserved!=BB[I].Reserved||AB[I].Delivered!=BB[I].Delivered
           ||AB[I].Collected!=BB[I].Collected||std::abs(AB[I].CollectionRemaining-BB[I].CollectionRemaining)>1.e-6)return false;
    return true;
}
bool MPRConserved(const MPRSorter::Simulation& S)
{
    const auto& T=S.GetStats();std::set<uint64_t> Ids;uint64_t Occupancy=0,Delivered=0,Collected=0;
    int Reserved=0,Unloading=0;
    for(const auto& C:S.GetCarriers())
    {
        if(C.ParcelId&&!Ids.insert(C.ParcelId).second)return false;
        if(C.State==MPRSorter::CarrierPhase::Unload)++Unloading;
        if(!std::isfinite(C.Distance01)||C.Distance01<0||C.Distance01>=1)return false;
    }
    for(const auto& B:S.GetBins())
    {
        if(B.Occupancy<0||B.Reserved<0||B.Occupancy+B.Reserved>B.Capacity)return false;
        Occupancy+=B.Occupancy;Reserved+=B.Reserved;Delivered+=B.Delivered;Collected+=B.Collected;
    }
    return T.Spawned==T.Completed+Ids.size()&&T.Active==int(Ids.size())
        &&T.Completed==Occupancy+T.Collected&&T.Completed==Delivered&&T.Collected==Collected&&Reserved==Unloading;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterConfiguration,"MPR.Sorter.Configuration",MPRFlags)
bool FMPRSorterConfiguration::RunTest(const FString&)
{
    MPRSorter::Simulation S;std::string Error;auto C=MPRFixture();
    TestTrue(TEXT("complete measured plan and explicit height profile accepted"),S.Initialize(C,Error));
    TestFalse(TEXT("starts paused"),S.IsPlaying());
    auto Bad=C;Bad.DestinationDistances01.pop_back();TestFalse(TEXT("missing station rejected"),S.Initialize(Bad,Error));
    TestFalse(TEXT("failure explains missing data"),Error.empty());
    Bad=C;Bad.LevelHeightsCm[0]=std::numeric_limits<double>::quiet_NaN();TestFalse(TEXT("nonfinite height rejected"),S.Initialize(Bad,Error));
    Bad=C;Bad.DestinationDistances01[0]=0;TestFalse(TEXT("destination cannot coincide with loading point"),S.Initialize(Bad,Error));
    Bad=C;Bad.OrderSequence={{2,0,0}};TestFalse(TEXT("invalid demonstration destination rejected"),S.Initialize(Bad,Error));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterFrameEquivalence,"MPR.Sorter.DeterministicFramePartition",MPRFlags)
bool FMPRSorterFrameEquivalence::RunTest(const FString&)
{
    MPRSorter::Simulation A,B,C;std::string Error;A.Initialize(MPRFixture(),Error);B.Initialize(MPRFixture(),Error);C.Initialize(MPRFixture(),Error);
    A.SetPlaying(true);B.SetPlaying(true);C.SetPlaying(true);
    TestTrue(TEXT("large accepted step processes all events"),A.Advance(173.125));
    TestTrue(TEXT("accepted frame advances time and completes actual parcels"),std::abs(A.GetStats().SimTime-173.125)<1.e-8&&A.GetStats().Completed>0);
    for(int I=0;I<17312;++I)B.Advance(.01);B.Advance(.005);
    C.Advance(73.125);C.Advance(100);
    TestTrue(TEXT("small and large frame partitions have identical state"),MPRSame(A,B));
    TestTrue(TEXT("unequal frame partitions preserve scan and unload boundary events"),MPRSame(A,C));
    TestTrue(TEXT("all parcels conserved"),MPRConserved(A)&&MPRConserved(B)&&MPRConserved(C));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterSharedChain,"MPR.Sorter.SharedChainAndUniqueParcels",MPRFlags)
bool FMPRSorterSharedChain::RunTest(const FString&)
{
    MPRSorter::Simulation S;std::string Error;S.Initialize(MPRFixture(),Error);S.SetPlaying(true);
    bool Spacing=true,Conservation=true,ReachedEveryBin=true;
    for(int Step=0;Step<12000;++Step)
    {
        S.Advance(.1);const auto& C=S.GetCarriers();
        for(int I=1;I<MPRSorter::CarrierCount;++I)
        {
            double D=std::fmod(C[I].Distance01-C[0].Distance01+1.,1.);
            Spacing&=std::abs(D-I*.25)<1.e-8;
        }
        Conservation&=MPRConserved(S);
    }
    for(const auto& B:S.GetBins())ReachedEveryBin&=B.Delivered>0;
    TestTrue(TEXT("four carriers never overtake or drift apart"),Spacing);
    TestTrue(TEXT("unique IDs and conservation hold through repeated collections"),Conservation);
    TestTrue(TEXT("both sides and every column/height are physically reached"),ReachedEveryBin);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterPauseReset,"MPR.Sorter.PauseRateAndReset",MPRFlags)
bool FMPRSorterPauseReset::RunTest(const FString&)
{
    MPRSorter::Simulation A,B;std::string Error;A.Initialize(MPRFixture(),Error);B.Initialize(MPRFixture(),Error);
    A.SetPlaying(true);A.Advance(15);A.SetPlaying(false);auto Paused=A;
    TestTrue(TEXT("pause has a meaningful moving simulation to freeze"),Paused.GetStats().Spawned>0&&Paused.GetStats().SimTime==15.);
    A.Advance(100);TestTrue(TEXT("pause freezes phase, lift, timers and counts"),MPRSame(A,Paused));
    A.SetPlaying(true);A.SetRate(4);A.Advance(20);B.SetPlaying(true);B.Advance(95);
    TestTrue(TEXT("4x rate changes only simulation time"),MPRSame(A,B));
    A.Reset();B.Reset();TestFalse(TEXT("reset pauses"),A.IsPlaying());TestEqual(TEXT("reset restores 1x"),A.GetRate(),1.);
    TestTrue(TEXT("reset clears all carriers, cells, time and counters"),MPRSame(A,B));
    A.SetPlaying(true);B.SetPlaying(true);A.SetRate(2);A.Advance(40);B.Advance(80);
    TestTrue(TEXT("2x has deterministic new demonstration sequence"),MPRSame(A,B));
    auto Before=A;TestFalse(TEXT("invalid speed rejected"),A.SetRate(3));TestTrue(TEXT("invalid speed does not mutate state"),MPRSame(A,Before));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterCapacity,"MPR.Sorter.FullBinStopsAndRecovers",MPRFlags)
bool FMPRSorterCapacity::RunTest(const FString&)
{
    auto C=MPRFixture();C.BinCapacity=1;C.AutoCollect=false;C.OrderSequence={{0,1,3}};
    MPRSorter::Simulation S;std::string Error;S.Initialize(C,Error);S.SetPlaying(true);S.Advance(120);
    TestEqual(TEXT("only one parcel entered full bin"),S.GetStats().Completed,uint64_t(1));
    TestTrue(TEXT("full destination reports chain blockage"),S.GetStats().ChainStopped&&S.GetStats().Reason==MPRSorter::BlockReason::FullBin);
    const auto Before=S.GetCarriers();S.Advance(100);
    bool Fixed=true;for(int I=0;I<MPRSorter::CarrierCount;++I)Fixed&=std::abs(Before[I].Distance01-S.GetCarriers()[I].Distance01)<1.e-10;
    TestTrue(TEXT("blocked chain cannot pass through the full bin"),Fixed&&MPRConserved(S));
    TestTrue(TEXT("simulated operator can empty target bin"),S.ClearBin({0,1,3}));S.Advance(2);
    TestEqual(TEXT("waiting parcel unloads once after clearing"),S.GetStats().Completed,uint64_t(2));
    TestEqual(TEXT("clear accounts for removed parcel"),S.GetStats().Collected,uint64_t(1));
    S.SetAutoCollect(true);S.Advance(120);
    TestTrue(TEXT("automatic collection restores repeated progress"),S.GetStats().Completed>2&&MPRConserved(S));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterLiftGate,"MPR.Sorter.LiftAndUnloadAreGated",MPRFlags)
bool FMPRSorterLiftGate::RunTest(const FString&)
{
    auto C=MPRFixture();C.DestinationDistances01[0]=.001;C.OrderSequence={{0,0,3}};C.LiftSpeedCmS=5;C.AutoCollect=false;
    MPRSorter::Simulation S;std::string Error;S.Initialize(C,Error);S.SetPlaying(true);S.Advance(1);
    TestTrue(TEXT("chain waits for a high destination instead of passing under it"),S.GetStats().Reason==MPRSorter::BlockReason::Lifting&&S.GetStats().ChainStopped);
    TestEqual(TEXT("not counted before height and ejection complete"),S.GetStats().Completed,uint64_t(0));
    bool SawUnload=false,CorrectHeight=true;
    for(int I=0;I<2000;++I)
    {
        S.Advance(.01);
        for(const auto& Carrier:S.GetCarriers())if(Carrier.State==MPRSorter::CarrierPhase::Unload)
        {SawUnload=true;CorrectHeight&=std::abs(Carrier.LiftHeightCm-C.LevelHeightsCm[3])<1.e-7&&Carrier.UnloadProgress>=0&&Carrier.UnloadProgress<=1;}
    }
    TestTrue(TEXT("unload animation occurs only at the selected height"),SawUnload&&CorrectHeight);
    TestTrue(TEXT("completed unload preserves parcels"),S.GetStats().Completed>0&&MPRConserved(S));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterLargeStep,"MPR.Sorter.LargeStepNoSkippedEvents",MPRFlags)
bool FMPRSorterLargeStep::RunTest(const FString&)
{
    MPRSorter::Simulation A,B;std::string Error;A.Initialize(MPRFixture(),Error);B.Initialize(MPRFixture(),Error);
    A.SetPlaying(true);B.SetPlaying(true);A.SetRate(4);A.Advance(900);
    TestTrue(TEXT("large step advances a complete simulated hour"),std::abs(A.GetStats().SimTime-3600.)<1.e-7&&A.GetStats().Completed>50);
    for(int I=0;I<36000;++I)B.Advance(.1);
    TestTrue(TEXT("one 4x frame matches one hour stepped at 1x"),MPRSame(A,B));
    TestTrue(TEXT("no duplication, capacity overflow or loss"),MPRConserved(A));
    const auto Before=A;
    TestFalse(TEXT("NaN delta rejected"),A.Advance(std::numeric_limits<double>::quiet_NaN()));
    TestFalse(TEXT("unbounded delta rejected explicitly"),A.Advance(std::numeric_limits<double>::max()));
    TestTrue(TEXT("rejected deltas do not partially advance"),MPRSame(A,Before));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterCollection,"MPR.Sorter.CollectionTimerAndUnloadReservation",MPRFlags)
bool FMPRSorterCollection::RunTest(const FString&)
{
    auto C=MPRFixture();C.BinCapacity=1;C.AutoCollect=false;C.OrderSequence={{1,1,2}};
    MPRSorter::Simulation S;std::string Error;S.Initialize(C,Error);S.SetPlaying(true);
    bool Found=false;
    for(int Step=0;Step<3000&&!Found;++Step)
    {
        S.Advance(.01);
        for(const auto& Item:S.GetCarriers())Found|=Item.State==MPRSorter::CarrierPhase::Unload;
    }
    TestTrue(TEXT("test reaches the real unloading transition"),Found);
    const int Index=S.BinIndex(C.OrderSequence[0]);
    TestEqual(TEXT("incoming parcel reserves one slot before delivery"),S.GetBins()[Index].Reserved,1);
    S.ClearBin(C.OrderSequence[0]);
    TestEqual(TEXT("collection cannot erase an unloading reservation"),S.GetBins()[Index].Reserved,1);
    S.Advance(60);TestEqual(TEXT("disabled collection leaves the full bin intact"),S.GetStats().Collected,uint64_t(0));
    S.SetAutoCollect(true);S.Advance(11.9);
    TestEqual(TEXT("enabling collection waits the full twelve simulated seconds"),S.GetStats().Collected,uint64_t(0));
    S.Advance(.101);
    TestEqual(TEXT("timed simulated operator empties once"),S.GetStats().Collected,uint64_t(1));
    TestTrue(TEXT("collection boundary does not lose the waiting parcel"),MPRConserved(S));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterCollectionDuringUnload,"MPR.Sorter.CollectionWaitsForOccupiedBinUnload",MPRFlags)
bool FMPRSorterCollectionDuringUnload::RunTest(const FString&)
{
    auto C=MPRFixture();C.BinCapacity=3;C.AutoCollect=true;C.CollectSeconds=3.25;C.OrderSequence={{0,0,0}};
    MPRSorter::Simulation S;std::string Error;S.Initialize(C,Error);S.SetPlaying(true);
    const int Index=S.BinIndex(C.OrderSequence[0]);
    bool Found=false;double UnloadRemaining=0.;
    for(int Step=0;Step<1000&&!Found;++Step)
    {
        S.Advance(.01);const auto& B=S.GetBins()[Index];
        for(const auto& Item:S.GetCarriers())if(Item.State==MPRSorter::CarrierPhase::Unload&&Item.Target==C.OrderSequence[0])
        {
            UnloadRemaining=(1.-Item.UnloadProgress)*C.UnloadSeconds;
            Found=B.Occupancy==1&&B.Reserved==1&&B.CollectionRemaining>.05&&B.CollectionRemaining+.05<UnloadRemaining;
        }
    }
    TestTrue(TEXT("occupied bin has a second unload crossing its collection deadline"),Found);
    if(!Found)return false;

    auto Manual=S;const auto BeforeManual=Manual;
    TestFalse(TEXT("manual collection rejects a bin while an incoming parcel is reserved"),Manual.ClearBin(C.OrderSequence[0]));
    TestTrue(TEXT("rejected pickup preserves the entire bin and counters"),MPRSame(Manual,BeforeManual));

    const auto AtUnload=S;const double PastDeadline=S.GetBins()[Index].CollectionRemaining+.05;
    TestTrue(TEXT("expiry during unloading still advances without a zero-step loop"),S.Advance(PastDeadline));
    TestEqual(TEXT("existing parcel stays put until incoming unloading completes"),S.GetBins()[Index].Occupancy,1);
    TestEqual(TEXT("incoming parcel keeps its reservation after collection expires"),S.GetBins()[Index].Reserved,1);
    TestEqual(TEXT("expired pickup waits without collecting any parcel"),S.GetStats().Collected,uint64_t(0));
    TestTrue(TEXT("deferred deadline reaches zero and conservation holds"),S.GetBins()[Index].CollectionRemaining<=1.e-9&&MPRConserved(S));

    TestTrue(TEXT("finishing unloading permits the deferred collection"),S.Advance(UnloadRemaining-PastDeadline+.01));
    TestEqual(TEXT("both delivered parcels are accounted once"),S.GetStats().Completed,uint64_t(2));
    TestEqual(TEXT("the completed occupied bin is collected together"),S.GetStats().Collected,uint64_t(2));
    TestEqual(TEXT("deferred collection empties the bin after unloading"),S.GetBins()[Index].Occupancy,0);
    TestEqual(TEXT("no stale incoming reservation remains"),S.GetBins()[Index].Reserved,0);

    auto Large=AtUnload,Small=AtUnload;const double Total=UnloadRemaining+.01;
    TestTrue(TEXT("one large step crosses collection and unloading boundaries"),Large.Advance(Total));
    const int Frames=1000;bool SmallSteps=true;
    for(int I=0;I<Frames;++I)SmallSteps&=Small.Advance(Total/Frames);
    TestTrue(TEXT("small steps all advance across the deferred collection"),SmallSteps);
    TestTrue(TEXT("large, small and event-split steps produce identical state"),MPRSame(Large,Small)&&MPRSame(Large,S));
    TestTrue(TEXT("deferred pickup preserves total parcel counts"),MPRConserved(S)&&MPRConserved(Large)&&MPRConserved(Small));
    return true;
}
#endif
