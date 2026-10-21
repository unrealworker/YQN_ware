#include "GHSDisplayStartup.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UnrealClient.h"
#include "UnrealEngine.h"
#include "Widgets/SWindow.h"

namespace GHSDisplayStartup
{
namespace
{
FDelegateHandle ViewportCreatedHandle;
FDelegateHandle WindowObservationHandle;
FVector2D LastWindowSize=FVector2D::ZeroVector;
int32 LastWindowMode=INDEX_NONE;
int32 WindowSamples=0;
double FirstWindowTime=0.;

void ObserveInitialWindow(float)
{
    auto& Slate=FSlateApplication::Get();
    for(const auto& Window:Slate.GetTopLevelWindows())
    {
        if(Window->GetType()!=EWindowType::GameWindow || !Window->IsVisible()) continue;
        const FVector2D Size=Window->GetClientSizeInScreen();
        const int32 Mode=int32(Window->GetWindowMode());
        if(!FirstWindowTime) FirstWindowTime=FPlatformTime::Seconds();
        if(Size!=LastWindowSize || Mode!=LastWindowMode)
        {
            ++WindowSamples;
            UE_LOG(LogTemp,Display,TEXT("GHS_DISPLAY_WINDOW_SHAPE sample=%d elapsed=%.3f client=%.0fx%.0f mode=%d"),
                WindowSamples,FPlatformTime::Seconds()-FirstWindowTime,Size.X,Size.Y,Mode);
            LastWindowSize=Size; LastWindowMode=Mode;
        }
        break;
    }
    if(FirstWindowTime && FPlatformTime::Seconds()-FirstWindowTime>=10.)
    {
        UE_LOG(LogTemp,Display,TEXT("GHS_DISPLAY_STARTUP_OBSERVED shapeChanges=%d"),FMath::Max(0,WindowSamples-1));
        Slate.OnPostTick().Remove(WindowObservationHandle);
        WindowObservationHandle.Reset();
    }
}

void LogCreatedViewport()
{
    if(!GEngine || !GEngine->GameViewport) return;
    const auto Window=GEngine->GameViewport->GetWindow();
    const FVector2D Client=Window.IsValid()?Window->GetClientSizeInScreen():FVector2D::ZeroVector;
    const FIntPoint Viewport=GEngine->GameViewport->Viewport?GEngine->GameViewport->Viewport->GetSizeXY():FIntPoint::ZeroValue;
    UE_LOG(LogTemp,Display,TEXT("GHS_DISPLAY_WINDOW_CREATED client=%.0fx%.0f viewport=%dx%d system=%dx%d mode=%d"),
        Client.X,Client.Y,Viewport.X,Viewport.Y,GSystemResolution.ResX,GSystemResolution.ResY,int32(GSystemResolution.WindowMode));
}
}

FRequest BuildRequest(const TCHAR* CommandLine,bool bPackagedInteractiveGame,FIntPoint DesktopResolution)
{
    FRequest Request;
    if(!bPackagedInteractiveGame || DesktopResolution.X<=0 || DesktopResolution.Y<=0) return Request;
    for(const TCHAR* Flag : {TEXT("Windowed"),TEXT("Fullscreen"),TEXT("WindowedFullscreen"),TEXT("RenderOffscreen"),TEXT("ForceRes"),TEXT("SimMobile")})
        if(FParse::Param(CommandLine,Flag)) return Request;
    FString Value;
    for(const TCHAR* Key : {TEXT("Res="),TEXT("ResX="),TEXT("ResY="),TEXT("WinX="),TEXT("WinY=")})
        if(FParse::Value(CommandLine,Key,Value)) return Request;
    Request.bApply=true;
    Request.Resolution=DesktopResolution;
    return Request;
}

void Startup()
{
#if PLATFORM_WINDOWS && !WITH_EDITOR
    if(IsRunningCommandlet() || IsRunningDedicatedServer() || !FApp::CanEverRender()) return;

    // This UObject-free module loads at PostSplashScreen, after InitHighDPI and
    // before PreLoadScreenManager creates the first game window. Settings preload runs before DPI
    // initialization in UE 5.4, so it can cache the 150%-DPI virtual desktop size.
    // Resolve the physical desktop here, once, while no game window is visible.
    FDisplayMetrics Display;
    FDisplayMetrics::RebuildDisplayMetrics(Display);
    const auto Request=BuildRequest(FCommandLine::Get(),true,FIntPoint(Display.PrimaryDisplayWidth,Display.PrimaryDisplayHeight));
    if(!Request.bApply) return;

    UE_LOG(LogTemp,Display,TEXT("GHS_DISPLAY_STARTUP desktop=%dx%d previous=%dx%d previousMode=%d requestedMode=%d"),
        Request.Resolution.X,Request.Resolution.Y,GSystemResolution.ResX,GSystemResolution.ResY,
        int32(GSystemResolution.WindowMode),int32(Request.WindowMode));
    FSystemResolution::RequestResolutionChange(Request.Resolution.X,Request.Resolution.Y,Request.WindowMode);
    IConsoleManager::Get().CallAllConsoleVariableSinks();
    ViewportCreatedHandle=UGameViewportClient::OnViewportCreated().AddStatic(&LogCreatedViewport);
    if(FSlateApplication::IsInitialized())
        WindowObservationHandle=FSlateApplication::Get().OnPostTick().AddStatic(&ObserveInitialWindow);
#endif
}

void Shutdown()
{
    if(WindowObservationHandle.IsValid() && FSlateApplication::IsInitialized())
        FSlateApplication::Get().OnPostTick().Remove(WindowObservationHandle);
    WindowObservationHandle.Reset();
    if(ViewportCreatedHandle.IsValid())
    {
        UGameViewportClient::OnViewportCreated().Remove(ViewportCreatedHandle);
        ViewportCreatedHandle.Reset();
    }
}
}
