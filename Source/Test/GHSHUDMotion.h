#pragma once

#include "CoreMinimal.h"

/** Local label fades: screen-space regrouping must never create long travel. */
namespace GHSHUDMotion
{
constexpr float Duration = .12f;
constexpr double MaxLocalDrift = 8.0;
constexpr double RelocationDistance = 64.0;

inline FVector2D BoundOffset(FVector2D Offset)
{
    const double Length = Offset.Size();
    return Length > MaxLocalDrift ? Offset * (MaxLocalDrift / Length) : Offset;
}

inline FVector2D EntryOffset() { return FVector2D(0, 6); }

inline float Progress(float Time)
{
    const float T = FMath::Clamp(Time / Duration, 0.f, 1.f);
    return T * T * (3 - 2 * T);
}

inline FVector2D EnterPosition(FVector2D Target, FVector2D StartOffset, float Progress)
{
    return Target + BoundOffset(StartOffset) * (1.f - FMath::Clamp(Progress, 0.f, 1.f));
}

inline FVector2D FollowPosition(FVector2D Current, FVector2D Target, float DeltaSeconds)
{
    return Target + BoundOffset((Current - Target) * FMath::Exp(-24.f * FMath::Max(DeltaSeconds, 0.f)));
}

inline bool IsRelocation(FVector2D PreviousTarget, FVector2D Target)
{
    return (Target - PreviousTarget).SizeSquared() > RelocationDistance * RelocationDistance;
}
}
