#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSOrderReplaySimulation.h"
#include "Misc/AutomationTest.h"
#include <limits>
#include <cmath>

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
    TestTrue(TEXT("partial and reversed retraversals merged"),std::abs(Total-20.)<.02);
    return true;
}
#endif
