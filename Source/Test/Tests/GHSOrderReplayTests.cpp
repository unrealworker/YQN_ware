#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSOrderReplaySimulation.h"
#include "Misc/AutomationTest.h"
#include <limits>
#include <cmath>
#include <algorithm>
#include <map>

namespace
{
GHSReplay::Simulation Fixture()
{
    GHSReplay::Simulation S;S.CycleDuration=100;
    for(int I=0;I<GHSReplay::EntityCount;++I)
    {
        auto& T=S.Tracks[I];T.Id="entity-"+std::to_string(I);
        T.Keys={{0,{0,0,0},0,0,0,true,-1,"idle"},{100,{0,0,0},0,0,0,true,-1,"idle"}};
    }
    S.Tracks[0].Keys={{0,{0,0,0},0,0,0,true,-1,"idle"},{50,{100,200,0},90,20,0,true,-1,"moving"},{100,{0,0,0},0,0,0,true,-1,"idle"}};
    S.Events={{10,"pickup","entity-0","pickup","Pickup"},{90,"drop","entity-0","dropoff","Drop"}};return S;
}
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayDirectSeek,"GHS.Replay.Motion.DirectSeek",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayDirectSeek::RunTest(const FString&)
{
    auto A=Fixture(),B=Fixture();std::string Error;TestTrue(TEXT("valid bounded fixture"),A.Validate(Error));
    for(double T=0;T<157.25;T+=.013)A.Evaluate(T);A.Evaluate(157.25);B.Evaluate(157.25);
    TestEqual(TEXT("seek equals incremental playback"),A.Poses[0].Position.X,B.Poses[0].Position.X);
    TestEqual(TEXT("seek yaw equals playback"),A.Poses[0].Yaw,B.Poses[0].Yaw);
    A.Evaluate(20);const auto Earlier=A.Poses[0];A.Evaluate(10000020);
    TestEqual(TEXT("large cycle count does not accumulate drift"),A.Poses[0].Position.X,Earlier.Position.X);
    A.Evaluate(0);const auto Start=A.Poses[0];A.Evaluate(100);
    TestEqual(TEXT("cycle boundary continuous"),A.Poses[0].Position.X,Start.Position.X);
    A.Evaluate(std::numeric_limits<double>::quiet_NaN());TestEqual(TEXT("nonfinite clock is guarded"),A.Poses[0].Position.X,0.);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayCargoOwnership,"GHS.Replay.Motion.CargoOwnership",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayCargoOwnership::RunTest(const FString&)
{
    auto S=Fixture();auto& Cargo=S.Tracks[8];
    Cargo.Keys={{0,{0,0,0},0,0,0,true,-1,"ground"},{20,{20,0,5},0,0,0,true,0,"fork"},{60,{5,0,0},0,0,0,true,5,"truck"},{80,{0,0,0},0,0,0,true,-1,"ground"},{100,{0,0,0},0,0,0,true,-1,"ground"}};
    S.Evaluate(19.9);TestEqual(TEXT("no world/local blending before pickup"),S.Poses[8].Position.X,0.);
    S.Evaluate(50);TestEqual(TEXT("one owner after pickup"),S.Poses[8].Owner,0);
    TestTrue(TEXT("pallet follows yawed forklift"),std::abs(S.Poses[8].Position.X-100.)<1.e-8);
    TestTrue(TEXT("pallet follows fork lift height"),std::abs(S.Poses[8].Position.Z-25.)<1.e-8);
    S.Evaluate(60);TestEqual(TEXT("drop changes owner exactly once"),S.Poses[8].Owner,5);
    TestEqual(TEXT("truck attachment position"),S.Poses[8].Position.X,5.);
    S.Evaluate(50);TestEqual(TEXT("rewind restores prior owner"),S.Poses[8].Owner,0);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayEventWindow,"GHS.Replay.Motion.BoundedEvents",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayEventWindow::RunTest(const FString&)
{
    auto S=Fixture();const auto E=S.EventsIn(95,215,3);
    TestEqual(TEXT("bounded lazy events across cycle"),int(E.size()),3);
    TestEqual(TEXT("cycle event absolute time"),E[0].Time,110.);
    TestEqual(TEXT("inclusive final event"),E[2].Time,210.);
    TestEqual(TEXT("huge window remains bounded"),int(S.EventsIn(0,1.e12,7).size()),7);
    S.Events.clear();TestTrue(TEXT("empty events returns immediately for huge interval"),S.EventsIn(0,1.e15,7).empty());
    std::string Error;S=Fixture();S.Events[1].Time=1;TestFalse(TEXT("unsorted source events rejected"),S.Validate(Error));
    S=Fixture();S.Tracks[0].Keys.back().Position.X=1;TestFalse(TEXT("visible cycle teleport rejected"),S.Validate(Error));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayCompleteTrails,"GHS.Replay.Motion.CompleteTrails",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayCompleteTrails::RunTest(const FString&)
{
    GHSReplay::Track T;
    T.Keys={{0,{0,0,0}},{1,{1000,0,0}},{2,{1000,500,0}},{3,{1000,0,0}},{4,{500,0,0}},{5,{500,0,0}},{6,{0,0,0}},{7,{0,200,0}},
        {8,{0,200,0},0,0,0,false},{9,{100000,0,0},0,0,0,false},{10,{100000,0,0}},{11,{100300,0,0}}};
    const auto Segments=GHSReplay::BuildTrailSegments(T);double Total=0;bool HasDockBranch=false,HasArrival=false;
    for(const auto& Segment:Segments)
    {
        Total+=Segment.LengthMeters;
        HasDockBranch|=Segment.A.Y>100||Segment.B.Y>100;
        HasArrival|=Segment.A.X>=100000&&Segment.B.X>=100000;
        TestTrue(TEXT("hidden pool teleport is never a trail"),Segment.LengthMeters<=10.01);
    }
    TestTrue(TEXT("pickup/dock branches retained"),HasDockBranch);
    TestTrue(TEXT("separate visible arrival retained"),HasArrival);
    TestTrue(TEXT("rounded branches keep bounded total length"),Total>19.&&Total<23.);
    T.Keys={{0,{0,0,0}},{1,{1000,0,0}},{2,{500,0,0}},{3,{500,0,0}},{4,{0,0,0}}};
    Total=0;for(const auto& Segment:GHSReplay::BuildTrailSegments(T))Total+=Segment.LengthMeters;
    TestTrue(TEXT("partial and reversed straight retraversals merged"),std::abs(Total-10.)<.0001);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayRoundedTrails,"GHS.Replay.Motion.RoundedForkliftTrails",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayRoundedTrails::RunTest(const FString&)
{
    GHSReplay::Track T;T.Keys={{0,{0,0,0}},{1,{1000,0,0}},{2,{1000,0,0}},{3,{1000,1000,0}}};
    const auto Segments=GHSReplay::BuildTrailSegments(T);
    TestTrue(TEXT("turn has curved samples instead of two square bars"),Segments.size()>20);
    double MaximumDeviation=0,MaximumGap=0;
    for(size_t I=0;I<Segments.size();++I)
    {
        const auto& S=Segments[I];
        for(const auto& P:{S.A,S.B})MaximumDeviation=std::max(MaximumDeviation,std::min(std::abs(P.Y),std::abs(P.X-1000.)));
        if(I+1>=Segments.size())continue;
        const auto& N=Segments[I+1];
        const double L=std::hypot(S.B.X-S.A.X,S.B.Y-S.A.Y),NL=std::hypot(N.B.X-N.A.X,N.B.Y-N.A.Y);
        const GHSReplay::Vec U{(S.B.X-S.A.X)/L,(S.B.Y-S.A.Y)/L},V{(N.B.X-N.A.X)/NL,(N.B.Y-N.A.Y)/NL};
        for(double Sign:{-1.,1.})
        {
            const double AX=S.B.X+Sign*(-U.Y*GHSReplay::TrailWidthCm*.5+U.X*S.EndShearCm);
            const double AY=S.B.Y+Sign*( U.X*GHSReplay::TrailWidthCm*.5+U.Y*S.EndShearCm);
            const double BX=N.A.X+Sign*(-V.Y*GHSReplay::TrailWidthCm*.5+V.X*N.StartShearCm);
            const double BY=N.A.Y+Sign*( V.X*GHSReplay::TrailWidthCm*.5+V.Y*N.StartShearCm);
            MaximumGap=std::max(MaximumGap,std::hypot(AX-BX,AY-BY));
        }
    }
    TestTrue(TEXT("curve stays within the measured path's 25cm presentation envelope"),MaximumDeviation<=25.0001);
    TestTrue(TEXT("miter corners form a watertight ribbon"),MaximumGap<.001);
    for(int I=0;I<GHSReplay::ForkCount;++I)
    {
        TestTrue(TEXT("forklift owns a visible color"),std::string(GHSReplay::TrailColor(I)).size()==7);
        for(int J=0;J<I;++J)TestTrue(TEXT("each forklift has a different color"),std::string(GHSReplay::TrailColor(I))!=GHSReplay::TrailColor(J));
    }
    for(int I=GHSReplay::ForkCount;I<GHSReplay::DeviceCount;++I)TestTrue(TEXT("trucks have no route color"),std::string(GHSReplay::TrailColor(I)).empty());
    T.Keys={{0,{0,0,0}},{1,{1000,0,0}},{2,{1000,50,0}},{3,{2000,50,0}}};
    bool Tapered=false;
    for(const auto& Segment:GHSReplay::BuildTrailSegments(T))
    {
        Tapered|=Segment.StartHalfWidthCm<GHSReplay::TrailWidthCm*.5;
        TestTrue(TEXT("short pickup bend has a positive inside edge"),Segment.LengthMeters*100.>std::abs(Segment.EndShearCm-Segment.StartShearCm));
        TestTrue(TEXT("local taper never disappears"),Segment.StartHalfWidthCm>0&&Segment.EndHalfWidthCm>0);
    }
    TestTrue(TEXT("tight pickup bend is tapered instead of folding"),Tapered);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayContinuousFlow,"GHS.Replay.Motion.ContinuousTrailFlow",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayContinuousFlow::RunTest(const FString&)
{
    GHSReplay::Track T;T.Keys={{0,{0,0,0}},{1,{1000,0,0}},{2,{1000,1000,0}},{3,{0,1000,0}},{4,{0,0,0}},
        {5,{1000,0,0}},{6,{1000,1000,0}},{7,{0,1000,0}},{8,{0,0,0}}};
    const auto Segments=GHSReplay::BuildTrailSegments(T);
    std::map<std::array<long long,2>,double> Junctions;bool Reversed=false;int Shared=0;
    for(const auto& S:Segments)
    {
        Reversed|=S.FlowDeltaMeters<0;
        TestTrue(TEXT("phase interpolation never runs faster than its path metric"),std::abs(S.FlowDeltaMeters)<=S.LengthMeters+.00001);
        for(int End=0;End<2;++End)
        {
            const auto& P=End?S.B:S.A;const std::array<long long,2> K{std::llround(P.X*100.),std::llround(P.Y*100.)};
            // Match the actual float custom-data and real Plane u=0/u=1 endpoints.
            const double Phase=float(S.StartMeters)+End*double(float(S.FlowDeltaMeters));
            const auto Existing=Junctions.find(K);
            if(Existing==Junctions.end())Junctions.emplace(K,Phase);
            else {++Shared;TestTrue(TEXT("a repeated trip shares its physical junction light phase"),std::abs(Existing->second-Phase)<.0001);}
        }
    }
    TestTrue(TEXT("loop includes shared path junctions"),Shared>20);
    TestTrue(TEXT("return-side phases can be signed without reversing geometry"),Reversed);
    return true;
}
#endif
