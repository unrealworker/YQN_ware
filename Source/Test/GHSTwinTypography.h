#pragma once
#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"

/** Visible glyph bounds used by MakeText, including the font's baseline and descender. */
struct FGHSTwinTextMetrics
{
    FVector2D Size=FVector2D::ZeroVector;
    double InkTop=0,InkBottom=0;
    double CenteredOriginY(double Height) const { return Height*.5-(InkTop+InkBottom)*.5; }
};
namespace GHSTwinTypography
{
    TEST_API FGHSTwinTextMetrics Measure(const FString& Text,const FSlateFontInfo& Font);
}
