#pragma once

#include "CoreMinimal.h"
#include "GenericPlatform/GenericWindow.h"

namespace GHSDisplayStartup
{
struct FRequest
{
    bool bApply=false;
    FIntPoint Resolution=FIntPoint::ZeroValue;
    EWindowMode::Type WindowMode=EWindowMode::WindowedFullscreen;
};

/** Decide the default without changing any window, settings file, or command line. */
GHSDISPLAYBOOTSTRAP_API FRequest BuildRequest(const TCHAR* CommandLine,bool bPackagedInteractiveGame,FIntPoint DesktopResolution);
void Startup();
void Shutdown();
}
