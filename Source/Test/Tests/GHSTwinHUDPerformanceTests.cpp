#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTwinHUDWidget.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinPOICadenceTest,"GHS.TwinUI.Performance.POICandidatesRespectCadenceAndInvalidation",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinPOICadenceTest::RunTest(const FString&)
{
    FGHSTwinPOIRefreshPolicy Policy;
    TestTrue(TEXT("First frame builds candidates"),Policy.Consume(0,1,false));
    for(int32 Frame=1;Frame<6;++Frame)
        TestFalse(TEXT("Unchanged candidate list survives intervening 60Hz frames"),Policy.Consume(Frame/60.,1,false));
    TestTrue(TEXT("100ms refresh picks up aggregate movement"),Policy.Consume(.1,1,false));
    TestTrue(TEXT("Telemetry/catalog revision invalidates without waiting"),Policy.Consume(.11,2,false));
    TestTrue(TEXT("Crossing aggregate distance threshold invalidates immediately"),Policy.Consume(.12,2,true));
    Policy.Invalidate();
    TestTrue(TEXT("Selection/filter/layer/density events invalidate immediately"),Policy.Consume(.13,2,true));
    TestFalse(TEXT("Consumed dirty event does not rebuild next frame"),Policy.Consume(.14,2,true));
    TestTrue(TEXT("Clock reset cannot hold stale candidates indefinitely"),Policy.Consume(0,2,true));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinBrowserVisibilityTest,"GHS.TwinUI.Performance.BrowserRefreshFollowsSlideVisibility",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinBrowserVisibilityTest::RunTest(const FString&)
{
    for(FVector2D Size:{FVector2D(1920,1080),FVector2D(600,900)})
    {
        const auto Layout=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        TestTrue(TEXT("Open browser refreshes"),GHSTwinHUDPerformance::ShouldRefreshBrowser(false,Motion.Progress));
        Motion.Advance(.21f,true);
        TestTrue(TEXT("Visible outgoing half retains content updates"),GHSTwinHUDPerformance::ShouldRefreshBrowser(true,Motion.Progress));
        TestTrue(TEXT("Geometry is still inside viewport halfway"),Motion.Position(Layout).X<Size.X);
        Motion.Advance(.21f,true);
        TestFalse(TEXT("Only fully hidden browser pauses"),GHSTwinHUDPerformance::ShouldRefreshBrowser(true,Motion.Progress));
        TestTrue(TEXT("Reopening resumes before first animation frame"),GHSTwinHUDPerformance::ShouldRefreshBrowser(false,Motion.Progress));
    }
    return true;
}
#endif
