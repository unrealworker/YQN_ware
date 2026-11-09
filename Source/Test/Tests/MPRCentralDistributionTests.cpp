#if WITH_DEV_AUTOMATION_TESTS || defined(MPR_CENTRAL_STANDALONE)
#include "../MPRCentralDistribution.h"
#include "../MPRSorterSimulation.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#ifdef MPR_CENTRAL_STANDALONE
#include <iostream>
using FString=std::string;
#define TEXT(X) X
static int MPRCentralFailures=0;
struct MPRCentralTestBase { void TestTrue(const char* Message,bool Value) {if(!Value){++MPRCentralFailures;std::cerr<<"FAIL: "<<Message<<'\n';}} };
#define IMPLEMENT_SIMPLE_AUTOMATION_TEST(Type,Name,Flags) struct Type:MPRCentralTestBase { bool RunTest(const FString&); };
#else
#include "GHSAutomationTestFlags.h"
#endif
namespace
{
#ifndef MPR_CENTRAL_STANDALONE
constexpr auto MPRCentralFlags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
#endif
MPRCentral::Config CentralFixture()
{
    MPRCentral::Config C;C.LoopLengthCm=1000;C.SpeedCmS=100;C.CarrierCount=4;
    C.FeedDistances01={0,.5};C.TargetDistances01={.15,.35,.65,.85};
    C.LoadingSeconds=.4;C.TransferSeconds=.25;return C;
}
bool CentralNear(double A,double B) {return std::abs(A-B)<1.e-7;}
bool CentralConserved(const MPRCentral::Simulation& S)
{
    std::set<uint64_t> Ids;std::vector<int> Targets(S.GetConfig().TargetDistances01.size(),0);
    const auto& C=S.GetCarriers();const auto& T=S.GetStats();
    for(size_t I=0;I<C.size();++I)
    {
        const auto& P=C[I];
        if(!std::isfinite(P.Distance01)||P.Distance01<0||P.Distance01>=1||P.Progress01<0||P.Progress01>1)return false;
        if(P.ParcelId)
        {
            if(!Ids.insert(P.ParcelId).second||P.TargetIndex<0
               ||P.TargetIndex>=int(S.GetConfig().TargetDistances01.size())||P.SourceStation<0
               ||P.SourceStation>=int(S.GetConfig().FeedDistances01.size())||P.Phase==MPRCentral::CarrierPhase::EmptyReturn)return false;
            if(++Targets[P.TargetIndex]>S.GetConfig().MaxPendingPerTarget)return false;
        }
        else if(P.Phase==MPRCentral::CarrierPhase::Recovering)
        {
            if(P.TargetIndex<0||P.SourceStation<0)return false;
        }
        else if(P.Phase!=MPRCentral::CarrierPhase::EmptyReturn||P.TargetIndex!=-1)return false;
        if(I&&!CentralNear(std::fmod(P.Distance01-C[0].Distance01+1.,1.),double(I)/C.size()))return false;
    }
    return T.Generated==T.Delivered+Ids.size()&&T.Active==int(Ids.size());
}
bool CentralSame(const MPRCentral::Simulation& A,const MPRCentral::Simulation& B)
{
    const auto& X=A.GetStats();const auto& Y=B.GetStats();
    if(X.Generated!=Y.Generated||X.Delivered!=Y.Delivered||X.Active!=Y.Active||X.BlockedPasses!=Y.BlockedPasses
       ||X.LoopStopped!=Y.LoopStopped||!CentralNear(X.SimTime,Y.SimTime)||!CentralNear(X.LoopPhase01,Y.LoopPhase01))return false;
    if(A.GetCarriers().size()!=B.GetCarriers().size())return false;
    for(size_t I=0;I<A.GetCarriers().size();++I)
    {
        const auto& P=A.GetCarriers()[I];const auto& Q=B.GetCarriers()[I];
        if(P.ParcelId!=Q.ParcelId||P.SourceStation!=Q.SourceStation||P.TargetIndex!=Q.TargetIndex||P.Phase!=Q.Phase
           ||!CentralNear(P.Distance01,Q.Distance01)||!CentralNear(P.Progress01,Q.Progress01))return false;
    }
    return A.IsFeedingEnabled()==B.IsFeedingEnabled()&&A.GetFeedCounts()==B.GetFeedCounts();
}
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralAdmission,"MPR.CentralDistribution.ConfigurationAndSimultaneousStations",MPRCentralFlags)
bool FMPRCentralAdmission::RunTest(const FString&)
{
    MPRCentral::Simulation S;std::string E;auto C=CentralFixture();uint64_t Next=1;
    auto Can=[](int){return true;};auto Take=[](int,uint64_t){return true;};
    TestTrue(TEXT("uninitialized loop cannot advance"),!S.Advance(1,Next,Can,Take));
    TestTrue(TEXT("explicit bank geometry initializes paused"),S.Initialize(C,E)&&!S.IsPlaying());
    S.SetPlaying(true);S.Advance(2.3,Next,Can,Take);
    int Loading=0;std::set<int> Sources;
    for(const auto& P:S.GetCarriers())if(P.Phase==MPRCentral::CarrierPhase::Loading){++Loading;Sources.insert(P.SourceStation);}
    TestTrue(TEXT("both simultaneous feed arrivals retain separate source workers and fixed carrier spacing"),Loading==2
        &&Sources==std::set<int>{0,1}&&Next==3&&S.GetStats().Generated==2&&!S.GetStats().LoopStopped&&CentralConserved(S));
    const auto Before=S;auto Bad=C;Bad.TargetDistances01[0]=Bad.FeedDistances01[0];
    TestTrue(TEXT("overlapping stations are rejected without replacing live state"),!S.Initialize(Bad,E)&&!E.empty()&&CentralSame(S,Before));
    Bad=C;Bad.SpeedCmS=std::numeric_limits<double>::quiet_NaN();TestTrue(TEXT("nonfinite speed rejected"),!S.Initialize(Bad,E));
    Bad=C;Bad.RecoverySeconds=0;TestTrue(TEXT("empty lift recovery requires a positive duration"),!S.Initialize(Bad,E));
    Bad=C;Bad.CarrierCount=0;TestTrue(TEXT("absent carrier pool rejected"),!S.Initialize(Bad,E));
    TestTrue(TEXT("invalid deltas and missing ownership callbacks do not mutate state"),!S.Advance(-1,Next,Can,Take)
        &&!S.Advance(std::numeric_limits<double>::infinity(),Next,Can,Take)&&!S.Advance(1,Next,{},Take)&&CentralSame(S,Before));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralBackpressure,"MPR.CentralDistribution.BlockedParcelRecirculation",MPRCentralFlags)
bool FMPRCentralBackpressure::RunTest(const FString&)
{
    auto C=CentralFixture();C.CarrierCount=1;C.MaxPendingPerTarget=1;C.FeedDistances01={.032};C.TargetDistances01={.5};
    MPRCentral::Simulation S;std::string E;S.Initialize(C,E);S.SetPlaying(true);uint64_t Next=81;
    bool Permit=true,AcceptPermit=false;int AcceptCalls=0;std::vector<uint64_t> Accepted;
    auto Can=[&](int){return Permit;};auto Take=[&](int,uint64_t Id){++AcceptCalls;if(AcceptPermit)Accepted.push_back(Id);return AcceptPermit;};
    bool Good=S.Advance(.1,Next,Can,Take);Permit=false;
    for(int I=0;I<600;++I)Good&=S.Advance(.05,Next,Can,Take)&&CentralConserved(S);
    TestTrue(TEXT("unavailable branch keeps the same parcel circulating without stopping the whole loop"),Good
        &&S.GetStats().Generated==1&&S.GetStats().Delivered==0&&S.GetStats().BlockedPasses>=2&&AcceptCalls==0
        &&S.GetCarriers()[0].ParcelId==81&&!S.GetStats().LoopStopped&&CentralNear(S.GetStats().LoopPhase01,.01));
    Permit=true;bool SawRetraction=false,Returned=false,RetractionGood=true;double LastRetractionProgress=-1;
    for(int I=0;I<1200&&!Returned;++I)
    {
        Good&=S.Advance(.01,Next,Can,Take)&&CentralConserved(S);
        const auto& P=S.GetCarriers()[0];
        if(P.Phase==MPRCentral::CarrierPhase::Retracting)
        {
            SawRetraction=true;RetractionGood&=P.ParcelId==81&&P.TargetIndex==0&&P.SourceStation==0
                &&P.Distance01>=.5-1.e-7&&!S.GetStats().LoopStopped&&P.Progress01>=LastRetractionProgress;
            LastRetractionProgress=P.Progress01;
            auto Frozen=S;Frozen.SetPlaying(false);const auto Before=Frozen;const auto BeforeId=Next;
            Frozen.Advance(10,Next,Can,Take);RetractionGood&=CentralSame(Frozen,Before)&&Next==BeforeId;
        }
        else if(SawRetraction&&P.Phase==MPRCentral::CarrierPhase::Travel)Returned=true;
    }
    TestTrue(TEXT("admission revoked at transfer completion retains original ownership for a later lap"),AcceptCalls>0
        &&S.GetStats().Delivered==0&&S.GetCarriers()[0].ParcelId==81&&CentralConserved(S));
    TestTrue(TEXT("failed discharge retracts visibly to its moving carrier and remains pausable"),SawRetraction
        &&Returned&&RetractionGood&&LastRetractionProgress>.9);
    AcceptPermit=true;bool SawTransfer=false;
    for(int I=0;I<1000&&Accepted.empty();++I)
    {
        Good&=S.Advance(.02,Next,Can,Take)&&CentralConserved(S);
        SawTransfer|=S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::Discharging;
    }
    TestTrue(TEXT("the original ID transfers exactly once after a moving discharge"),Good&&SawTransfer
        &&Accepted==std::vector<uint64_t>{81}&&S.GetStats().Delivered==1&&Next==82);
    const auto AtHandoff=S;const auto Delivered=S.GetStats().Delivered;const auto Branch=S.GetCarriers()[0].Distance01;
    TestTrue(TEXT("successful discharge retains an empty recovery tray at the branch"),S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::Recovering
        &&S.GetCarriers()[0].ParcelId==0&&S.GetCarriers()[0].TargetIndex==0&&S.GetCarriers()[0].SourceStation==0
        &&!S.GetStats().LoopStopped&&CentralConserved(S));
    S.Advance(C.RecoverySeconds*.45,Next,Can,Take);
    TestTrue(TEXT("empty tray lifts continuously while the shared chain keeps moving"),S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::Recovering
        &&S.GetCarriers()[0].Progress01>AtHandoff.GetCarriers()[0].Progress01&&CentralNear(S.GetCarriers()[0].Distance01,Branch+.045)
        &&S.GetStats().Delivered==Delivered&&Accepted.size()==1&&CentralConserved(S));
    const double RecoveryRemaining=(1.-S.GetCarriers()[0].Progress01)*C.RecoverySeconds;
    S.Advance(RecoveryRemaining,Next,Can,Take);
    TestTrue(TEXT("empty return begins only after lift recovery completes without another handoff"),S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::EmptyReturn
        &&S.GetCarriers()[0].TargetIndex==-1&&!S.GetStats().LoopStopped&&S.GetCarriers()[0].Distance01>Branch+.09
        &&S.GetStats().Delivered==Delivered&&Accepted.size()==1&&CentralConserved(S));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralClock,"MPR.CentralDistribution.PauseResetAndFramePartition",MPRCentralFlags)
bool FMPRCentralClock::RunTest(const FString&)
{
    MPRCentral::Simulation A,B;std::string E;A.Initialize(CentralFixture(),E);B.Initialize(CentralFixture(),E);
    uint64_t IA=1,IB=1;std::vector<uint64_t> DA,DB;auto Can=[](int){return true;};
    auto TakeA=[&](int,uint64_t Id){DA.push_back(Id);return true;};auto TakeB=[&](int,uint64_t Id){DB.push_back(Id);return true;};
    A.SetPlaying(true);B.SetPlaying(true);bool Good=A.Advance(120,IA,Can,TakeA);
    for(int I=0;I<1200;++I)Good&=B.Advance(.1,IB,Can,TakeB)&&CentralConserved(B);
    TestTrue(TEXT("exact stop events preserve IDs and spacing across large and small frame partitions"),Good
        &&CentralSame(A,B)&&IA==IB&&DA==DB&&CentralConserved(A));
    A.SetPlaying(false);const auto Paused=A;const auto BeforeId=IA;A.Advance(300,IA,Can,TakeA);
    TestTrue(TEXT("pause freezes global clock poses parcels and ID consumption"),CentralSame(A,Paused)&&IA==BeforeId);
    A.Reset();B.Reset();
    TestTrue(TEXT("reset clears all ownership and motion and pauses without rewinding shared IDs"),CentralSame(A,B)
        &&!A.IsPlaying()&&A.GetStats().Generated==0&&IA==BeforeId&&CentralConserved(A));
    IA=std::numeric_limits<uint64_t>::max();A.SetPlaying(true);A.Advance(40,IA,Can,TakeA);
    TestTrue(TEXT("shared ID exhaustion never wraps or duplicates a parcel"),IA==0&&A.GetStats().Generated==1
        &&A.GetStats().Delivered==1&&CentralConserved(A));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralContinuous,"MPR.CentralDistribution.ContinuousLoadedAndEmptyCirculation",MPRCentralFlags)
bool FMPRCentralContinuous::RunTest(const FString&)
{
    MPRCentral::Simulation S;std::string E;const auto C=CentralFixture();uint64_t Next=1;
    S.Initialize(C,E);S.SetPlaying(true);bool Continuous=true;int Phases=0;
    auto Can=[](int){return true;};auto Take=[](int,uint64_t){return true;};
    for(int I=1;I<=1200;++I)
    {
        Continuous&=S.Advance(.05,Next,Can,Take);
        Continuous&=CentralNear(S.GetStats().LoopPhase01,std::fmod(I*.05*C.SpeedCmS/C.LoopLengthCm,1.))&&!S.GetStats().LoopStopped;
        for(const auto& P:S.GetCarriers())Phases|=1<<int(P.Phase);
    }
    TestTrue(TEXT("loading unloading and empty lift never stop or slow the common chain"),Continuous
        &&(Phases&(1<<int(MPRCentral::CarrierPhase::Loading)))&&(Phases&(1<<int(MPRCentral::CarrierPhase::Discharging)))
        &&(Phases&(1<<int(MPRCentral::CarrierPhase::Recovering))));
    // Disabled feeding models completed incoming work. Empty equipment must
    // keep moving indefinitely, not shut down when the last parcel is delivered.
    S.SetFeedingEnabled(false);S.Advance(40,Next,Can,Take);const auto Before=S.GetStats();
    S.Advance(3,Next,Can,Take);
    TestTrue(TEXT("finished sorting keeps all empty carriers circulating"),S.GetStats().Active==0&&S.IsPlaying()
        &&S.GetStats().Generated==Before.Generated&&S.GetStats().Delivered==Before.Delivered&&!S.GetStats().LoopStopped
        &&CentralNear(S.GetStats().LoopPhase01,std::fmod(Before.LoopPhase01+.3,1.)));
    const auto BeforeId=Next;S.SetFeedingEnabled(true);S.Advance(5,Next,Can,Take);
    TestTrue(TEXT("restarting feed does not require restarting the continuously moving loop"),Next>BeforeId&&S.IsPlaying()&&!S.GetStats().LoopStopped);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralMovingPorts,"MPR.CentralDistribution.MovingPortAlignmentAndConcurrentPhases",MPRCentralFlags)
bool FMPRCentralMovingPorts::RunTest(const FString&)
{
    auto C=CentralFixture();C.CarrierCount=1;C.FeedDistances01={.032};C.TargetDistances01={.5};
    MPRCentral::Simulation S;std::string E;uint64_t Next=1;bool AtOutput=false;
    TestTrue(TEXT("moving port fixture initializes"),S.Initialize(C,E));S.SetPlaying(true);
    auto Can=[](int){return true;};auto Take=[&](int,uint64_t Id)
    {AtOutput=Id==1&&CentralNear(S.GetCarriers()[0].Distance01,.5);return true;};
    S.Advance(C.LoadingSeconds*C.FeedHandoffProgress,Next,Can,Take);
    TestTrue(TEXT("upstream preparation aligns the moving tray with the fixed feeding port at handoff"),
        S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::Loading
        &&CentralNear(S.GetCarriers()[0].Progress01,C.FeedHandoffProgress)
        &&CentralNear(S.GetCarriers()[0].Distance01,C.FeedDistances01[0]));
    S.Advance(5.-C.LoadingSeconds*C.FeedHandoffProgress,Next,Can,Take);
    TestTrue(TEXT("side transfer finishes exactly at the fixed machine port without stopping"),AtOutput
        &&S.GetCarriers()[0].Phase==MPRCentral::CarrierPhase::Recovering&&!S.GetStats().LoopStopped);
    auto Bad=C;Bad.MaxPendingPerTarget=0;TestTrue(TEXT("zero target reservations cannot silently stall feeding"),!S.Initialize(Bad,E));
    Bad=C;Bad.FeedHandoffProgress=1.5;TestTrue(TEXT("handoff must occur inside loading cycle"),!S.Initialize(Bad,E));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralBanks,"MPR.CentralDistribution.TwentyTwoTargetsAndGlobalIdentity",MPRCentralFlags)
bool FMPRCentralBanks::RunTest(const FString&)
{
    auto C=CentralFixture();C.LoopLengthCm=7500;C.CarrierCount=96;C.SpeedCmS=60;C.LoadingSeconds=1.2;
    C.TransferSeconds=.45;C.RecoverySeconds=.45;C.FeedDistances01={0,.01,.02,.5,.51,.52};
    C.TargetDistances01.clear();for(int I=0;I<18;++I)C.TargetDistances01.push_back(.04+I*.049);
    auto D=C;D.LoopLengthCm=2000;D.CarrierCount=24;D.FeedDistances01={0};D.TargetDistances01={.1,.3,.6,.8};
    MPRCentral::Simulation A,B;std::string E;bool Good=A.Initialize(C,E)&&B.Initialize(D,E);A.SetPlaying(true);B.SetPlaying(true);
    uint64_t Next=1;std::vector<int> Counts(22,0);std::vector<uint64_t> LastIds(22,0);std::set<uint64_t> Ids;bool Unique=true;
    auto Can=[](int){return true;};
    auto Take=[&](int Target,uint64_t Id){Unique&=Ids.insert(Id).second&&Id>LastIds[Target];LastIds[Target]=Id;++Counts[Target];return true;};
    auto TakeB=[&](int Target,uint64_t Id){return Take(Target+18,Id);};
    for(int I=0;I<12000;++I)
    {
        Good&=A.Advance(.25,Next,Can,Take)&&B.Advance(.25,Next,Can,TakeB)&&CentralConserved(A)&&CentralConserved(B);
    }
    TestTrue(TEXT("both CAD banks reach all 22 destinations with monotonic machine IDs from one global source"),Good&&Unique
        &&*std::min_element(Counts.begin(),Counts.end())>=2&&Next==A.GetStats().Generated+B.GetStats().Generated+1
        &&Ids.size()==A.GetStats().Delivered+B.GetStats().Delivered);
    const auto& Feeds=A.GetFeedCounts();
    TestTrue(TEXT("all six operators get repeated work without an upstream station monopolizing trays"),
        *std::min_element(Feeds.begin(),Feeds.end())>=20&&*std::max_element(Feeds.begin(),Feeds.end())-*std::min_element(Feeds.begin(),Feeds.end())<=1);
    TestTrue(TEXT("arrival-aware assignments avoid needless full laps just to preserve ID order"),
        A.GetStats().BlockedPasses==0&&B.GetStats().BlockedPasses==0);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCentralSorterHandoff,"MPR.CentralDistribution.SorterOwnershipAndCartReplacement",MPRCentralFlags)
bool FMPRCentralSorterHandoff::RunTest(const FString&)
{
    auto C=CentralFixture();C.CarrierCount=2;C.FeedDistances01={0};C.TargetDistances01={.5};
    MPRCentral::Simulation Central;MPRSorter::Simulation Sorter;std::string E;bool Good=Central.Initialize(C,E);
    MPRSorter::Config D;D.ExternalInfeed=true;D.Columns=1;D.Levels=1;D.BinCapacity=1;D.CartColumns=1;
    D.LoopLengthCm=1000;D.ChainSpeedCmS=140;D.LevelHeightsCm={D.LoadHeightCm};D.DestinationDistances01={.25,.75};
    Good&=Sorter.Initialize(D,E);Central.SetPlaying(true);Sorter.SetPlaying(true);uint64_t Next=1;
    std::set<uint64_t> Accepted;bool SameId=true,SawBlocked=false;
    auto Can=[&](int){return Sorter.CanAcceptExternalParcel();};
    auto Take=[&](int,uint64_t Id)
    {
        if(!Sorter.EnqueueExternalParcel(Id))return false;
        SameId&=Accepted.insert(Id).second&&Sorter.GetInfeedQueue().back().ParcelId==Id;return true;
    };
    for(int I=0;I<15000;++I)
    {
        Good&=Sorter.Advance(.02)&&Central.Advance(.02,Next,Can,Take)&&CentralConserved(Central);
        Good&=Sorter.GetStats().Spawned==Central.GetStats().Delivered;
        SawBlocked|=Central.GetStats().BlockedPasses>0;
    }
    TestTrue(TEXT("central distribution hands original IDs to real sorter intake and waits through complete cart changes"),Good&&SameId
        &&SawBlocked&&Sorter.GetStats().ExchangedCarts>=2&&Sorter.GetStats().Collected>=2
        &&Accepted.size()==Central.GetStats().Delivered);
    return true;
}
#ifdef MPR_CENTRAL_STANDALONE
int main()
{
    FMPRCentralAdmission().RunTest("");FMPRCentralBackpressure().RunTest("");FMPRCentralClock().RunTest("");
    FMPRCentralBanks().RunTest("");FMPRCentralSorterHandoff().RunTest("");
    FMPRCentralContinuous().RunTest("");
    FMPRCentralMovingPorts().RunTest("");
    std::cout<<"MPR central tests: "<<MPRCentralFailures<<" failures\n";return MPRCentralFailures?1:0;
}
#endif
#endif
