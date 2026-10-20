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
#endif
