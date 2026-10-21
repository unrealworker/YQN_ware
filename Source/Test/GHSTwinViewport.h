#pragma once
#include "CoreMinimal.h"

/** UI sizes are 1080p design units. Only viewport input/projection uses pixels. */
struct FGHSTwinViewport
{
    FVector2D PixelSize=FVector2D(1920,1080);
    FVector2D LogicalSize=PixelSize;
    double Scale=1.;

    static FGHSTwinViewport FromPixels(FVector2D Pixels)
    {
        FGHSTwinViewport Result;
        Result.PixelSize=FVector2D(FMath::Max(1.,Pixels.X),FMath::Max(1.,Pixels.Y));
        Result.Scale=FMath::Max(1.,FMath::Min(Result.PixelSize.X/1920.,Result.PixelSize.Y/1080.));
        Result.LogicalSize=Result.PixelSize/Result.Scale;
        return Result;
    }
    FVector2D ToLogical(FVector2D Pixels) const { return Pixels*LogicalSize/PixelSize; }
    FVector2D ToPixels(FVector2D Logical) const { return Logical*PixelSize/LogicalSize; }
    bool MatchesGeometry(FVector2D AllocatedSize) const { return AllocatedSize.Equals(LogicalSize,1.); }
    // SGameLayerManager already removes platform DPI before applying the project
    // curve. Cancel that curve once, then apply the warehouse design scale once.
    double SlateScale(double ProjectScale) const { return Scale/FMath::Max(.1,ProjectScale); }
};
