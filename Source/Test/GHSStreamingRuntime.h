#pragma once

#include "CoreMinimal.h"

/** Local launcher control only; never exposes a console or a network listener. */
namespace GHSStreamingRuntime
{
    struct FBudget
    {
        int64 Sequence = 0;
        int32 FPS = 60;
        double MinBitrateMbps = 1;
        double MaxBitrateMbps = 35;
    };

    bool ParseBudget(const FString& Json, FBudget& Out, FString& Error);
    bool ApplyBudget(const FBudget& Budget, int64& LastSequence, FString& Error);
    void Startup();
    void Shutdown();
}
