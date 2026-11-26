#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSTwinHeaderLayout.h"
#include "../GHSTwinLayout.h"
#include "../GHSTwinTypography.h"
#include "GHSAutomationTestFlags.h"
#include "Misc/Paths.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinHeaderReflow,
    "GHS.TwinUI.Layout.AddressClockReflowsAndKeepsInputBounds",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinHeaderReflow::RunTest(const FString&)
{
    auto Intersects=[](FVector2D A,FVector2D AS,FVector2D B,FVector2D BS)
    { return A.X<B.X+BS.X && A.X+AS.X>B.X && A.Y<B.Y+BS.Y && A.Y+AS.Y>B.Y; };
    for(double Width:{320.,390.,440.,563.,564.,600.,639.,640.,800.,999.,1000.,1024.,1249.,1250.,1366.,1920.,2560.})
    {
        const auto H=FGHSTwinHeaderLayout::Calculate(Width);
        const auto Scene=FGHSTwinLayout::Calculate(FVector2D(Width,900));
        TestFalse(TEXT("Address and clock never overlap"),Intersects(H.AddressPosition,H.AddressSize,H.ClockPosition,H.ClockSize));
        for(const auto& Item:{TPair<FVector2D,FVector2D>(H.AddressPosition,H.AddressSize),TPair<FVector2D,FVector2D>(H.ClockPosition,H.ClockSize),TPair<FVector2D,FVector2D>(H.ReturnButtonPosition,H.ReturnButtonSize)})
        {
            TestTrue(TEXT("Address, clock and return slot stay inside viewport"),Item.Key.X>=0 && Item.Key.X+Item.Value.X<=Width && Item.Key.Y>=0 && Item.Key.Y+Item.Value.Y<=H.Height);
            TestFalse(TEXT("Information does not overlap the panel toggle"),Intersects(Item.Key,Item.Value,H.PanelButtonPosition,H.PanelButtonSize));
            TestFalse(TEXT("Information does not toggle the panel"),H.IsPanelButton(Item.Key+Item.Value*.5));
            TestFalse(TEXT("Information cannot select objects behind the header"),Scene.IsScenePoint(Item.Key+Item.Value*.5));
        }
        TestFalse(TEXT("Return never covers the address"),Intersects(H.ReturnButtonPosition,H.ReturnButtonSize,H.AddressPosition,H.AddressSize));
        TestFalse(TEXT("Return never covers the clock"),Intersects(H.ReturnButtonPosition,H.ReturnButtonSize,H.ClockPosition,H.ClockSize));
        TestFalse(TEXT("Return never covers the brand"),Intersects(H.ReturnButtonPosition,H.ReturnButtonSize,FVector2D(22,0),FVector2D(H.bCompactBrand?184:258,H.BrandRowHeight)));
        TestTrue(TEXT("Return uses the compact header footprint"),H.ReturnButtonSize.Equals(FVector2D(136,36)));
        TestTrue(TEXT("Panel toggle center remains clickable"),H.IsPanelButton(H.PanelButtonPosition+H.PanelButtonSize*.5));
        TestFalse(TEXT("Below toggle is not another toggle target"),H.IsPanelButton(H.PanelButtonPosition+H.PanelButtonSize+FVector2D(-8,1)));
        TestEqual(TEXT("Scene begins below the complete header"),Scene.ScenePosition.Y,H.Height);
    }
    TestEqual(TEXT("1000 pixel header moves information below the return control"),FGHSTwinHeaderLayout::Calculate(1000).Height,112.);
    TestEqual(TEXT("1249 pixel header retains safe two-row layout"),FGHSTwinHeaderLayout::Calculate(1249).Height,112.);
    TestEqual(TEXT("1250 pixel header fits a single row"),FGHSTwinHeaderLayout::Calculate(1250).Height,64.);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSTwinHeaderGlyphs,
    "GHS.TwinUI.Layout.AddressClockTextFitsActualFont",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSTwinHeaderGlyphs::RunTest(const FString&)
{
    const FString Path=FPaths::ProjectContentDir()/TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf");
    const auto City=GHSTwinTypography::Measure(TEXT("San Bernardino, CA 92407 美国"),FSlateFontInfo(Path,11));
    const auto Date=GHSTwinTypography::Measure(TEXT("2026.12.31 · PST (UTC-08:00)"),FSlateFontInfo(Path,11));
    const auto Street=GHSTwinTypography::Measure(TEXT("17335 Glen Helen Pkwy"),FSlateFontInfo(Path,13));
    const auto Label=GHSTwinTypography::Measure(TEXT("仓库当地时间"),FSlateFontInfo(Path,11));
    TestTrue(TEXT("Measured font exists"),City.Size.X>0 && Date.Size.X>0);
    TestTrue(TEXT("Full city and street fit reserved address width"),City.Size.X<=242 && Street.Size.X<=242);
    TestTrue(TEXT("Date and offset fit reserved clock width"),Date.Size.X<=238);
    TestTrue(TEXT("Clock label fits before the fixed digits"),Label.Size.X<=94);
    const auto Brand=GHSTwinTypography::Measure(TEXT("GHS 数字孪生"),FSlateFontInfo(Path,17));
    TestTrue(TEXT("Compact brand leaves room for the narrow panel toggle"),57+Brand.Size.X<208);
    return true;
}
#endif
