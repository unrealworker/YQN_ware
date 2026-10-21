#if WITH_DEV_AUTOMATION_TESTS
#include "GHSDisplayStartup.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDesktopStartupDefaultTest,"GHS.Display.Startup.UsesCurrentDesktopBeforeWindowCreation",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSDesktopStartupDefaultTest::RunTest(const FString&)
{
    for(const FIntPoint Desktop : {FIntPoint(2560,1600),FIntPoint(1920,1080),FIntPoint(3840,2160)})
    {
        const auto Request=GHSDisplayStartup::BuildRequest(TEXT(""),true,Desktop);
        TestTrue(TEXT("A direct packaged launch gets a desktop fullscreen request"),Request.bApply);
        TestEqual(TEXT("Use the physical desktop, not a fixed 1080p or virtual DPI size"),Request.Resolution,Desktop);
        TestEqual(TEXT("Use borderless fullscreen without a display mode switch"),int32(Request.WindowMode),int32(EWindowMode::WindowedFullscreen));
    }
    TestFalse(TEXT("Editor and PIE keep their own window policy"),GHSDisplayStartup::BuildRequest(TEXT(""),false,FIntPoint(2560,1600)).bApply);
    TestFalse(TEXT("Missing display information cannot resize a window"),GHSDisplayStartup::BuildRequest(TEXT(""),true,FIntPoint::ZeroValue).bApply);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSDesktopStartupOverridesTest,"GHS.Display.Startup.PreservesExplicitResolutionAndWindowModes",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSDesktopStartupOverridesTest::RunTest(const FString&)
{
    const TCHAR* Commands[]={
        TEXT("-Windowed"),TEXT("-fullscreen"),TEXT("-RenderOffscreen"),TEXT("-ForceRes"),
        TEXT("-ResX=1920"),TEXT("-ResY=1080"),TEXT("-Res=1920x1080w"),TEXT("-WinX=2560 -WinY=0"),
        TEXT("-PixelStreamingURL=ws://127.0.0.1:8888 -ResX=1920 -ResY=1080 -ForceRes -RenderOffscreen"),
        TEXT("-ResX=1920 -ResY=1080 -Windowed")};
    for(const TCHAR* Command:Commands)
        TestFalse(Command,GHSDisplayStartup::BuildRequest(Command,true,FIntPoint(2560,1600)).bApply);
    TestTrue(TEXT("Unrelated diagnostics do not disable the desktop default"),GHSDisplayStartup::BuildRequest(TEXT("-NoSplash -TwinDiagnostics"),true,FIntPoint(2560,1600)).bApply);
    return true;
}
#endif
