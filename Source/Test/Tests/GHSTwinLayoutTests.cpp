#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTwinLayout.h"
#include "Misc/AutomationTest.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinAdaptiveLayout, "GHS.TwinUI.Layout.PreservesSceneAndReadablePanel", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSTwinAdaptiveLayout::RunTest(const FString& Parameters)
{
    for (FVector2D Size : {FVector2D(3840,2160), FVector2D(2560,1440), FVector2D(1920,1080), FVector2D(1366,768), FVector2D(1024,768), FVector2D(800,600), FVector2D(600,900), FVector2D(390,844)})
    {
        const auto L = FGHSTwinLayout::Calculate(Size);
        TestTrue(TEXT("Panel stays on screen"), L.PanelPosition.X >= 0 && L.PanelPosition.Y >= L.HeaderHeight && L.PanelPosition.X + L.PanelSize.X <= Size.X + .1 && L.PanelPosition.Y + L.PanelSize.Y <= Size.Y + .1);
        TestTrue(TEXT("Panel has readable width"), L.PanelSize.X >= FMath::Min(360., Size.X));
        TestTrue(TEXT("Scene remains visible and operable"), L.SceneSize.X >= FMath::Min(390.,Size.X) && L.SceneSize.Y >= 180);
        TestFalse(TEXT("Panel does not accept scene click"), L.IsScenePoint(L.PanelPosition + L.PanelSize * .5));
        TestTrue(TEXT("Scene centre accepts click"), L.IsScenePoint(L.ScenePosition + L.SceneSize * .5));
    }
    const auto Desktop = FGHSTwinLayout::Calculate(FVector2D(1920,1080));
    TestEqual(TEXT("Approved panel width at full HD"), Desktop.PanelSize.X, 480.);
    TestEqual(TEXT("Approved header height"), Desktop.HeaderHeight, 64.);
    const auto Portrait = FGHSTwinLayout::Calculate(FVector2D(600,900));
    TestEqual(TEXT("Portrait panel becomes bottom sheet"), Portrait.PanelPosition.X, 0.);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinPanelSlide, "GHS.TwinUI.Layout.PanelSlidesFullWidthAndReversesWithoutJump", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSTwinPanelSlide::RunTest(const FString&)
{
    for(FVector2D Size:{FVector2D(1920,1080),FVector2D(1366,768),FVector2D(600,900)})
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        const auto Start=Motion.Position(Expanded);
        Motion.Advance(.21f,true);
        const auto Middle=Motion.Position(Expanded);
        TestTrue(TEXT("Collapse moves right by half the actual panel width at midpoint"),FMath::IsNearlyEqual(Middle.X-Start.X,Expanded.PanelSize.X*.5,.01));
        TestEqual(TEXT("Narrow and wide panels never slide vertically"),Middle.Y,Start.Y);
        Motion.Advance(0,false);
        TestTrue(TEXT("Rapid reversal begins at its current position"),Motion.Position(Expanded).Equals(Middle,.001));
        Motion.Advance(.42f,false);
        TestTrue(TEXT("Expand returns precisely to the original position"),Motion.Position(Expanded).Equals(Start,.001));
        Motion.Advance(.42f,true);
        TestTrue(TEXT("Collapsed panel is fully beyond the right viewport edge"),FMath::IsNearlyEqual(Motion.Position(Expanded).X,Size.X,.001));
        Motion.Advance(.21f,false);
        TestTrue(TEXT("Expand travels left through an intermediate position"),Motion.Position(Expanded).X>Start.X && Motion.Position(Expanded).X<Size.X);
    }
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinControlsFollowPanel, "GHS.TwinUI.Layout.SceneControlsFollowPanelDuringSlide", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSTwinControlsFollowPanel::RunTest(const FString&)
{
    for(FVector2D Size:{FVector2D(3840,2160),FVector2D(1920,1080),FVector2D(1366,768),FVector2D(900,600)})
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        FVector2D Previous=Motion.SceneControlsPosition(Size);
        TestTrue(TEXT("Open controls have a 20px gap before the drawer"),FMath::IsNearlyEqual(Previous.X+60,Expanded.PanelPosition.X,.001));
        for(int32 Frame=0;Frame<28;++Frame)
        {
            Motion.Advance(1.f/60,true);
            const FVector2D Current=Motion.SceneControlsPosition(Size);
            TestTrue(TEXT("Each frame stays attached to the visible drawer edge"),FMath::IsNearlyEqual(Current.X+60,Motion.Position(Expanded).X,.001));
            TestTrue(TEXT("Closing controls move monotonically, without a final-frame snap"),Current.X>=Previous.X && Current.X-Previous.X<Expanded.PanelSize.X*.08);
            TestEqual(TEXT("Desktop controls keep their vertical alignment"),Current.Y,Previous.Y);
            Previous=Current;
        }
        TestTrue(TEXT("Hidden drawer leaves 20px right margin"),FMath::IsNearlyEqual(Previous.X+60,Size.X,.001));
        Motion.Advance(.14f,false);
        const FVector2D Reversal=Motion.SceneControlsPosition(Size);
        TestTrue(TEXT("Opening controls move left before the slide completes"),Reversal.X<Previous.X);
        Motion.Advance(0,true);
        TestTrue(TEXT("Reversing midway preserves control position"),Motion.SceneControlsPosition(Size).Equals(Reversal,.001));
        Motion.Advance(.42f,true);
        TestTrue(TEXT("Reversal still reaches the viewport margin"),FMath::IsNearlyEqual(Motion.SceneControlsPosition(Size).X+60,Size.X,.001));
    }
    for(FVector2D Size:{FVector2D(800,600),FVector2D(600,900),FVector2D(390,844)})
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        const FVector2D Start=Motion.SceneControlsPosition(Size);
        for(int32 Frame=0;Frame<28;++Frame)
        {
            Motion.Advance(1.f/60,true);
            const FVector2D Current=Motion.SceneControlsPosition(Size);
            TestTrue(TEXT("Narrow controls remain steady above the sliding bottom sheet"),Current.Equals(Start,.001));
            TestTrue(TEXT("Narrow controls remain visible and outside the browser"),Current.X>=0 && Current.X+40<=Size.X && Current.Y>=Expanded.HeaderHeight && Current.Y+112<=Expanded.PanelPosition.Y);
        }
    }
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinSearchFollowsPanel, "GHS.TwinUI.Layout.SceneSearchFollowsPanelDuringSlide", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSTwinSearchFollowsPanel::RunTest(const FString&)
{
    for(FVector2D Size:{FVector2D(3840,2160),FVector2D(1920,1080),FVector2D(1366,768),FVector2D(1024,768)})
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        const FVector2D Open=Motion.SceneSearchPosition(Size);
        FVector2D Previous=Open;
        for(int32 Frame=0;Frame<28;++Frame)
        {
            Motion.Advance(1.f/60,true);
            const FVector2D Current=Motion.SceneSearchPosition(Size);
            TestTrue(TEXT("Search keeps its 24px margin from the visible drawer on every frame"),FMath::IsNearlyEqual(Current.X+360+24,Motion.Position(Expanded).X,.001));
            TestTrue(TEXT("Search and scene controls move together"),FMath::IsNearlyEqual(Current.X+324,Motion.SceneControlsPosition(Size).X,.001));
            TestTrue(TEXT("Search collapse has no last-frame jump"),Current.X>=Previous.X && Current.X-Previous.X<Expanded.PanelSize.X*.08);
            TestEqual(TEXT("Search keeps its vertical position"),Current.Y,Open.Y);
            Previous=Current;
        }
        TestTrue(TEXT("Closed search reaches the viewport right margin"),FMath::IsNearlyEqual(Previous.X+384,Size.X,.001));
        Motion.Advance(.14f,false);
        const FVector2D Reversal=Motion.SceneSearchPosition(Size);
        TestTrue(TEXT("Search moves left before opening completes"),Reversal.X<Previous.X);
        Motion.Advance(0,true);
        TestTrue(TEXT("Search reversal starts at the current position"),Motion.SceneSearchPosition(Size).Equals(Reversal,.001));
        Motion.Advance(.42f,true);
        Motion.Advance(.42f,false);
        TestTrue(TEXT("Search returns precisely to its expanded position"),Motion.SceneSearchPosition(Size).Equals(Open,.001));
    }
    for(FVector2D Size:{FVector2D(800,600),FVector2D(600,900)})
    {
        const auto Expanded=FGHSTwinLayout::Calculate(Size);
        FGHSTwinPanelMotion Motion;
        const FVector2D Open=Motion.SceneSearchPosition(Size);
        for(int32 Frame=0;Frame<28;++Frame)
        {
            Motion.Advance(1.f/60,true);
            const FVector2D Current=Motion.SceneSearchPosition(Size);
            TestTrue(TEXT("Narrow search remains steady above the sliding bottom sheet"),Current.Equals(Open,.001));
            TestTrue(TEXT("Narrow search stays on screen and outside the bottom sheet"),Current.X>=140 && Current.X+360<=Size.X-24 && Current.Y>=Expanded.HeaderHeight && Current.Y+36<=Expanded.PanelPosition.Y);
        }
    }
    return true;
}
#endif
