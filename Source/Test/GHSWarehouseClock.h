#pragma once

#include "CoreMinimal.h"

/** Warehouse-local display derived from UTC, independent of the host time zone. */
struct TEST_API FGHSWarehouseClock
{
    FString TimeText;
    FString DateText;

    static FGHSWarehouseClock Format(const FDateTime& Utc);

    /** Returns true when a new UTC second, including a clock correction, is formatted. */
    bool Refresh(const FDateTime& Utc);

private:
    int64 CachedUtcSecond = MIN_int64;
};
