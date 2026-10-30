#pragma once

#include "CoreMinimal.h"

/** Local launcher control only; never exposes a console or a network listener. */
namespace GHSStreamingRuntime
{
    struct FBudget
    {
        int64 Sequence = 0;
        int32 FPS = 0; // Zero removes only the render cap; PS2 retains its positive negotiated capture ceiling.
        double MinBitrateMbps = 1;
        double MaxBitrateMbps = 35;
    };

    bool ParseBudget(const FString& Json, FBudget& Out, FString& Error);
    bool ApplyBudget(const FBudget& Budget, int64& LastSequence, FString& Error);
    struct FStartupOptions
    {
        FString Encoder = TEXT("Auto");
        int32 FixedFPS = 0;
    };
    bool ParseStartupOptions(const TCHAR* CommandLine, FStartupOptions& Out, FString& Error);
    bool ValidateNvidiaPolicy(bool bNvidiaRHI, bool bNVENCAPIAvailable, const FString& ActualCodec, bool bNegotiateCodecs, FString& Error);
    void Startup();
    void Shutdown();
}
