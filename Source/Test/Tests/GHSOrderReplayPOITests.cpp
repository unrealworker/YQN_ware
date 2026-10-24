#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSReplayPOILayout.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayPOIPlacementTest,"GHS.Replay.POI.AvoidsChromeTimelineAndOtherDevices",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayPOIPlacementTest::RunTest(const FString&)
{
    const FBox2D Bounds(FVector2D(8,72),FVector2D(1432,880));
    TArray<FBox2D> Blocked={FBox2D(FVector2D(24,80),FVector2D(280,164)),FBox2D(FVector2D(1056,80),FVector2D(1416,128))};
    TArray<FBox2D> Occupied;
    const FVector2D Size(236,42);
    for(const FVector2D Anchor:{FVector2D(650,450),FVector2D(672,452),FVector2D(675,460),FVector2D(650,472),FVector2D(700,470),FVector2D(620,475),FVector2D(725,460),FVector2D(600,450)})
    {
        FVector2D At;
        TestTrue(TEXT("All eight close devices receive a readable nonoverlapping label"),GHSReplayPOI::Place(Anchor,Size,Bounds,Blocked,Occupied,nullptr,At));
        const FBox2D Card(At,At+Size);
        TestTrue(TEXT("Whole card stays in scene above the timeline"),GHSReplayPOI::Contains(Bounds,Card));
        TestFalse(TEXT("A label never covers its own projected anchor"),Card.IsInside(Anchor));
        for(const auto& B:Blocked) TestFalse(TEXT("Labels avoid heading and search"),GHSReplayPOI::Intersects(Card,B,0));
        for(const auto& B:Occupied) TestFalse(TEXT("Cards have a gap instead of overwriting another device"),GHSReplayPOI::Intersects(Card,B,7));
        Occupied.Add(Card);
    }
    FVector2D At;
    TestFalse(TEXT("Offscreen anchors do not pin misleading edge POIs"),GHSReplayPOI::Place(FVector2D(-100,400),Size,Bounds,Blocked,Occupied,nullptr,At));
    const FVector2D Edge(1422,840);
    TestTrue(TEXT("An edge device may place its card inward"),GHSReplayPOI::Place(Edge,Size,Bounds,Blocked,{},nullptr,At));
    TestTrue(TEXT("Edge card remains above timeline"),GHSReplayPOI::Contains(Bounds,FBox2D(At,At+Size)));
    const FVector2D Previous=At;
    TestTrue(TEXT("A valid prior card offset is retained"),GHSReplayPOI::Place(Edge,Size,Bounds,Blocked,{},&Previous,At));
    TestTrue(TEXT("Stationary anchors do not jump among layouts"),At.Equals(Previous));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayPOISemanticsTest,"GHS.Replay.POI.PreservesFaultAndTaskStatus",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayPOISemanticsTest::RunTest(const FString&)
{
    TestEqual(TEXT("Fault remains red regardless of selected route colour"),GHSReplayPOI::StatusKind(TEXT("故障停机")),GHSReplayPOI::EStatus::Fault);
    TestEqual(TEXT("Waiting is distinguished from an active motion"),GHSReplayPOI::StatusKind(TEXT("等待作业")),GHSReplayPOI::EStatus::Waiting);
    TestEqual(TEXT("Yielding remains visible as a wait"),GHSReplayPOI::StatusKind(TEXT("交叉通道让行")),GHSReplayPOI::EStatus::Waiting);
    TestEqual(TEXT("Idle still has a POI and neutral status"),GHSReplayPOI::StatusKind(TEXT("待命")),GHSReplayPOI::EStatus::Idle);
    TestEqual(TEXT("Pickup action remains an active task state"),GHSReplayPOI::StatusKind(TEXT("抬升托盘")),GHSReplayPOI::EStatus::Active);
    TestEqual(TEXT("Long truck status is concise without losing meaning"),GHSReplayPOI::CompactStatus(TEXT("测试补给车 · 返回园区")),FString(TEXT("补给回场")));
    TestEqual(TEXT("Full fault wording is retained"),GHSReplayPOI::CompactStatus(TEXT("故障停机")),FString(TEXT("故障停机")));
    return true;
}
#endif
