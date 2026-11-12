#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRSorterSimulation.h"
#include "GHSAutomationTestFlags.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace
{
constexpr auto PresentationFlags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
using MPRSorter::CarrierPhase;
bool Near(double A,double B,double E=1.e-7){return std::abs(A-B)<E;}
double Forward(double A,double B){return std::fmod(B-A+1.,1.);}
bool SameCarrier(const MPRSorter::Carrier& A,const MPRSorter::Carrier& B)
{
    return A.State==B.State&&A.ParcelId==B.ParcelId&&A.Target==B.Target
        &&A.TargetCartIndex==B.TargetCartIndex&&A.TargetCartGeneration==B.TargetCartGeneration
        &&Near(A.Distance01,B.Distance01)&&Near(A.LiftHeightCm,B.LiftHeightCm)
        &&Near(A.ScanProgress,B.ScanProgress)&&Near(A.InductProgress,B.InductProgress)&&Near(A.UnloadProgress,B.UnloadProgress);
}
bool SameAuthority(const MPRSorter::Simulation& A,const MPRSorter::Simulation& B)
{
    const auto& X=A.GetStats();const auto& Y=B.GetStats();
    if(X.Spawned!=Y.Spawned||X.Completed!=Y.Completed||X.Collected!=Y.Collected||X.Active!=Y.Active
        ||X.Queued!=Y.Queued||X.ExchangedCarts!=Y.ExchangedCarts||X.Reason!=Y.Reason||X.ChainStopped!=Y.ChainStopped
        ||!Near(X.SimTime,Y.SimTime)||!Near(X.ChainPhase01,Y.ChainPhase01)||!Near(X.BlockedSeconds,Y.BlockedSeconds))return false;
    for(int I=0;I<MPRSorter::CarrierCount;++I)if(!SameCarrier(A.GetCarriers()[I],B.GetCarriers()[I]))return false;
    if(A.GetInfeedQueue().size()!=B.GetInfeedQueue().size())return false;
    for(size_t I=0;I<A.GetInfeedQueue().size();++I)
        if(A.GetInfeedQueue()[I].ParcelId!=B.GetInfeedQueue()[I].ParcelId
            ||!Near(A.GetInfeedQueue()[I].Progress01,B.GetInfeedQueue()[I].Progress01))return false;
    for(size_t I=0;I<A.GetBins().size();++I)
    {
        const auto& P=A.GetBins()[I];const auto& Q=B.GetBins()[I];
        if(P.Occupancy!=Q.Occupancy||P.Reserved!=Q.Reserved||P.Delivered!=Q.Delivered||P.Collected!=Q.Collected||P.ParcelIds!=Q.ParcelIds)return false;
    }
    for(size_t I=0;I<A.GetCarts().size();++I)
    {
        const auto& P=A.GetCarts()[I];const auto& Q=B.GetCarts()[I];
        if(P.State!=Q.State||P.Occupancy!=Q.Occupancy||P.Reserved!=Q.Reserved||P.Generation!=Q.Generation
            ||P.ParcelIds!=Q.ParcelIds||P.LastOutboundParcelIds!=Q.LastOutboundParcelIds||P.Collected!=Q.Collected||!Near(P.Progress01,Q.Progress01))return false;
    }
    return true;
}
MPRSorter::Config ContinuousFixture()
{
    MPRSorter::Config C;C.Columns=1;C.Levels=1;C.CartColumns=1;C.BinCapacity=1;
    C.LoopLengthCm=1000.;C.ChainSpeedCmS=100.;C.LevelHeightsCm={C.LoadHeightCm};
    C.DestinationDistances01={.95,.45};C.OrderSequence={{0,0,0}};
    C.ExternalInfeed=true;C.InfeedTravelSeconds=.2;C.ScanSeconds=.1;C.InductSeconds=.2;
    return C;
}
bool StartContinuous(MPRSorter::Simulation& S)
{
    std::string Error;if(!S.Initialize(ContinuousFixture(),Error))return false;
    S.SetPlaying(true);if(!S.EnqueueExternalParcel(101))return false;
    // One original parcel keeps the chain working while empty carriers cross
    // the load port without inducing new scan/stop events during this fixture.
    for(int I=0;I<100&&S.GetCarriers()[0].State!=CarrierPhase::LoadedTravel;++I)
        if(!S.Advance(.01))return false;
    return S.GetCarriers()[0].State==CarrierPhase::LoadedTravel&&!S.GetStats().ChainStopped;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterRenderFrameSampling,"MPR.Sorter.Presentation.RenderFrameSampling",PresentationFlags)
bool FMPRSorterRenderFrameSampling::RunTest(const FString&)
{
    const std::vector<std::vector<double>> Schedules={{1./60.},{1./120.},{.007,.019,.011,.031,.004,.023}};
    for(const auto& Frames:Schedules)for(double Rate:{1.,2.,4.})
    {
        MPRSorter::Simulation S;if(!TestTrue(TEXT("Single-parcel moving ring initializes"),StartContinuous(S)))return false;
        S.SetRate(Rate);const auto Initial=S.GetCarriers();
        double Residual=0.,Elapsed=0.;int RawHeldFrames=0,Wrapped=0;bool Smooth=true,Pure=true;
        auto LastDisplay=Initial;auto LastRaw=Initial;
        for(int Frame=0;Elapsed<8.;++Frame)
        {
            const double Delta=std::min(Frames[Frame%Frames.size()]*Rate,8.-Elapsed);
            Elapsed+=Delta;Residual+=Delta;
            while(Residual+1.e-10>=MPRSorter::MaxPresentationSeconds)
            {Smooth&=S.Advance(MPRSorter::MaxPresentationSeconds/Rate);Residual=std::max(0.,Residual-MPRSorter::MaxPresentationSeconds);}
            const auto Before=S;
            RawHeldFrames+=Near(S.GetCarriers()[0].Distance01,LastRaw[0].Distance01);
            LastRaw=S.GetCarriers();
            for(size_t I=0;I<Initial.size();++I)
            {
                const auto P=S.GetPresentationCarrier(I,Residual);
                const double Expected=std::fmod(Initial[I].Distance01+Elapsed*.1,1.);
                Smooth&=Near(std::remainder(P.Distance01-Expected,1.),0.)
                    &&Near(Forward(LastDisplay[I].Distance01,P.Distance01),Delta*.1)
                    &&Near(P.LiftHeightCm,Initial[I].LiftHeightCm);
                Wrapped+=P.Distance01<LastDisplay[I].Distance01;LastDisplay[I]=P;
            }
            Pure&=SameAuthority(S,Before);
        }
        TestTrue(TEXT("All four carriers advance each render frame at 60/120/irregular FPS and 1/2/4x, including loop wrap"),Smooth&&Wrapped>=3);
        TestTrue(TEXT("Fractional presentation leaves the fixed-step model untouched"),Pure);
        if(Rate==1.)TestTrue(TEXT("Fixture exposes the original repeated raw poses between scheduler ticks"),RawHeldFrames>100);
        const auto Last=S.GetPresentationCarrier(0,Residual);S.SetPlaying(false);const auto Frozen=S;S.Advance(20.);
        TestTrue(TEXT("Pause retains the exact displayed fractional pose"),SameCarrier(Last,S.GetPresentationCarrier(0,Residual))&&SameAuthority(S,Frozen));
        S.Reset();const auto Reset=S.GetPresentationCarrier(0,0.);
        TestTrue(TEXT("Reset with zero residual returns to initial unloaded pose"),Reset.Distance01==0.&&Reset.ParcelId==0&&Reset.State==CarrierPhase::EmptyReturn);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterRenderEventBoundaries,"MPR.Sorter.Presentation.StopBoundariesAndOwnership",PresentationFlags)
bool FMPRSorterRenderEventBoundaries::RunTest(const FString&)
{
    auto C=ContinuousFixture();C.ExternalInfeed=false;C.Levels=2;C.LevelHeightsCm={42.,180.};C.OrderSequence.clear();
    C.DestinationDistances01={.191,.713};C.ChainSpeedCmS=140.;C.ScanSeconds=.113;C.InductSeconds=.173;C.UnloadSeconds=.237;
    C.CollectSeconds=.3;C.CartWithdrawSeconds=.3;C.CartOutboundSeconds=.4;C.CartHandoffSeconds=.2;C.CartEmptyArrivalSeconds=.4;C.CartDockSeconds=.3;
    MPRSorter::Simulation S;std::string Error;
    if(!TestTrue(TEXT("Event-boundary fixture initializes"),S.Initialize(C,Error)))return false;
    S.SetPlaying(true);bool Bounded=true,Pure=true,QueueBounded=true;int Phases=0,AtStop=0,EndProgress=0,ExchangeFrames=0;
    for(int Step=0;Step<6000;++Step)
    {
        Bounded&=S.Advance(.05);const auto Before=S;
        for(size_t I=0;I<MPRSorter::CarrierCount;++I)
        {
            const auto& A=S.GetCarriers()[I];const auto P=S.GetPresentationCarrier(I,.049);Phases|=1<<int(A.State);
            Pure&=P.ParcelId==A.ParcelId&&P.State==A.State&&P.Target==A.Target
                &&P.TargetCartIndex==A.TargetCartIndex&&P.TargetCartGeneration==A.TargetCartGeneration;
            if(S.GetStats().ChainStopped)Bounded&=Near(P.Distance01,A.Distance01);
            else
            {
                const double Moved=Forward(A.Distance01,P.Distance01);
                Bounded&=Moved<=.049*C.ChainSpeedCmS/C.LoopLengthCm+1.e-8;
                if(A.State==CarrierPhase::LoadedTravel)
                {
                    const double Target=C.DestinationDistances01[size_t(A.Target.Side)];
                    double Remaining=Forward(A.Distance01,Target);if(Remaining<1.e-10)Remaining=1.;
                    Bounded&=Moved<=Remaining+1.e-8;
                    AtStop+=Remaining>.000001&&Near(Moved,Remaining);
                }
            }
            const double Height=A.State==CarrierPhase::EmptyReturn||A.State==CarrierPhase::Scan||A.State==CarrierPhase::Induct
                ?C.LoadHeightCm:C.LevelHeightsCm[size_t(A.Target.Level)];
            Bounded&=P.LiftHeightCm>=std::min(A.LiftHeightCm,Height)-1.e-7
                &&P.LiftHeightCm<=std::max(A.LiftHeightCm,Height)+1.e-7
                &&std::abs(P.LiftHeightCm-A.LiftHeightCm)<=.049*C.LiftSpeedCmS+1.e-7;
            for(double Progress:{P.ScanProgress,P.InductProgress,P.UnloadProgress})Bounded&=Progress>=0.&&Progress<=1.;
            EndProgress+=(A.State==CarrierPhase::Induct&&A.InductProgress<1.&&Near(P.InductProgress,1.))
                ||(A.State==CarrierPhase::Unload&&A.UnloadProgress<1.&&Near(P.UnloadProgress,1.));
            if(S.GetStats().Reason==MPRSorter::BlockReason::CartExchange)
            {++ExchangeFrames;Bounded&=SameCarrier(P,A);}
        }
        double Last=2.;const double Gap=1./double(C.InfeedCapacity+1);
        for(size_t I=0;I<S.GetInfeedQueue().size();++I)
        {
            const auto& A=S.GetInfeedQueue()[I];const auto P=S.GetPresentationInfeedParcel(I,.049);
            Pure&=P.ParcelId==A.ParcelId;
            QueueBounded&=P.Progress01>=A.Progress01-1.e-8&&P.Progress01<=1.-double(I)*Gap+1.e-8&&Last-P.Progress01>=Gap-1.e-8;
            Last=P.Progress01;
        }
        Pure&=SameAuthority(S,Before);
    }
    TestTrue(TEXT("Sampling stops at load/delivery ports and never crosses a lift, induction or cart-exchange boundary"),Bounded&&AtStop>0&&EndProgress>0&&ExchangeFrames>0);
    TestTrue(TEXT("Every physical carrier phase is exercised"),Phases==((1<<6)-1));
    TestTrue(TEXT("Presentation cannot reserve, hand off, deliver, collect or replace a real parcel/cart"),Pure&&S.GetStats().ExchangedCarts>1);
    TestTrue(TEXT("Infeed sampling preserves identity and safe queue spacing"),QueueBounded);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRSorterRenderIndependentSubstep,"MPR.Sorter.Presentation.IndependentSubstepAndInvalidResidual",PresentationFlags)
bool FMPRSorterRenderIndependentSubstep::RunTest(const FString&)
{
    MPRSorter::Simulation S;if(!TestTrue(TEXT("Independent moving fixture initializes"),StartContinuous(S)))return false;
    S.Advance(1.);
    for(double Rate:{1.,2.,4.})for(double Residual:{0.,.001,.008333333,.016666667,.034,.05})
    {
        S.SetRate(Rate);auto Reference=S;Reference.Advance(Residual/Rate);
        for(size_t I=0;I<MPRSorter::CarrierCount;++I)
            TestTrue(TEXT("Render-only sample matches a separately advanced physical model before any event"),SameCarrier(S.GetPresentationCarrier(I,Residual),Reference.GetCarriers()[I]));
    }
    TestTrue(TEXT("Oversized residual is limited to one fleet scheduling step"),SameCarrier(S.GetPresentationCarrier(0,100.),S.GetPresentationCarrier(0,.05)));
    for(double Bad:{-1.,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()})
        TestTrue(TEXT("Negative or nonfinite residual preserves the authoritative pose"),SameCarrier(S.GetPresentationCarrier(0,Bad),S.GetCarriers()[0]));
    TestTrue(TEXT("Missing carrier index is safe"),S.GetPresentationCarrier(100,.04).ParcelId==0);
    TestTrue(TEXT("Missing queue index is safe"),S.GetPresentationInfeedParcel(100,.04).ParcelId==0);
    return true;
}
#endif
