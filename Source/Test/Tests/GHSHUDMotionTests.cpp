#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSHUDMotion.h"
#include "Misc/AutomationTest.h"

namespace GHSHUDMotionTests
{
constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSHUDMotionLocalEntry,
    "GHS.DockTruckHUD.Motion.EntryStaysAtDestination", GHSHUDMotionTests::Flags)
bool FGHSHUDMotionLocalEntry::RunTest(const FString& Parameters)
{
    const FVector2D Target(1800, 900);
    // Even an obsolete source at the opposite corner must not produce a sweep
    // through the viewport. This also covers retargeting during a resize.
    const FVector2D StaleSourceOffset(-1700, -800);
    for (int32 Frame = 0; Frame <= 12; ++Frame)
    {
        const float Progress = GHSHUDMotion::Progress(Frame * 0.01f);
        const FVector2D Position = GHSHUDMotion::EnterPosition(Target, StaleSourceOffset, Progress);
        TestTrue(TEXT("Every intermediate sample remains within eight logical pixels of its destination"),
            FVector2D::Distance(Position, Target) <= 8.00001);
    }
    TestTrue(TEXT("At 120ms the label is exactly at the destination"),
        GHSHUDMotion::EnterPosition(Target, StaleSourceOffset, GHSHUDMotion::Progress(.12f)).Equals(Target, .00001));
    TestTrue(TEXT("Normal entry begins six logical pixels from the target"),
        GHSHUDMotion::EnterPosition(Target, GHSHUDMotion::EntryOffset(), 0).Equals(Target + FVector2D(0, 6), .00001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSHUDMotionFollowing,
    "GHS.DockTruckHUD.Motion.MovingDestinationCannotBuildLongLag", GHSHUDMotionTests::Flags)
bool FGHSHUDMotionFollowing::RunTest(const FString& Parameters)
{
    FVector2D Position(20, 20);
    const FVector2D Targets[] = { FVector2D(100, 100), FVector2D(1400, 200), FVector2D(300, 900), FVector2D(2100, 1000) };
    for (const FVector2D& Target : Targets)
    {
        Position = GHSHUDMotion::FollowPosition(Position, Target, 1.f / 60.f);
        TestTrue(TEXT("Camera motion never leaves the label sweeping toward a distant projection"),
            FVector2D::Distance(Position, Target) <= 8.00001);
    }
    const FVector2D CloseTarget = Position + FVector2D(3, 4);
    const FVector2D Followed = GHSHUDMotion::FollowPosition(Position, CloseTarget, 1.f / 60.f);
    TestTrue(TEXT("Small normal motion retains smoothing"),
        FVector2D::Distance(Followed, Position) > 0 && FVector2D::Distance(Followed, CloseTarget) > 0
        && FVector2D::Distance(Followed, CloseTarget) < 5);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSHUDMotionFastFade,
    "GHS.DockTruckHUD.Motion.FadeCompletesIn120Milliseconds", GHSHUDMotionTests::Flags)
bool FGHSHUDMotionFastFade::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("Fade starts invisible"), GHSHUDMotion::Progress(0), 0.f);
    TestTrue(TEXT("Animation has a real intermediate state"), GHSHUDMotion::Progress(.06f) > 0 && GHSHUDMotion::Progress(.06f) < 1);
    TestEqual(TEXT("Arrival and retirement finish at 120ms"), GHSHUDMotion::Progress(.12f), 1.f);
    TestEqual(TEXT("Long frames cannot overshoot opacity"), GHSHUDMotion::Progress(1), 1.f);
    TestFalse(TEXT("Ordinary projected motion is followed without a fade restart"),
        GHSHUDMotion::IsRelocation(FVector2D(10, 10), FVector2D(13, 14)));
    TestTrue(TEXT("Large relocation restarts a local fade"),
        GHSHUDMotion::IsRelocation(FVector2D(10, 10), FVector2D(900, 400)));
    return true;
}
#endif
