#include "GHSTwinTypography.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/FontCache.h"
#include "Fonts/FontMeasure.h"
#include "Rendering/SlateRenderer.h"

FGHSTwinTextMetrics GHSTwinTypography::Measure(const FString& Text,const FSlateFontInfo& Font)
{
    FGHSTwinTextMetrics Result;
    if(!FSlateApplication::IsInitialized()) return Result;
    const auto Renderer=FSlateApplication::Get().GetRenderer();
    Result.Size=Renderer->GetFontMeasureService()->Measure(Text,Font);
    auto& Characters=Renderer->GetFontCache()->GetCharacterList(Font,1.f);
    bool bHasInk=false;
    for(const TCHAR Character:Text)
    {
        const auto& Entry=Characters.GetCharacter(Character,Font.FontFallback);
        if(!Entry.Valid || Entry.VSize==0 || Entry.USize==0 || FChar::IsWhitespace(Character)) continue;
        // This is Slate's unshaped MakeText quad placement (ElementBatcher),
        // not the full line box returned by FontMeasure, whose leading varies.
        const double Top=-Entry.VerticalOffset+(Characters.GetMaxHeight()+Entry.GlobalDescender)/FMath::Max(.0001f,Entry.BitmapRenderScale);
        const double Bottom=Top+Entry.VSize*Entry.BitmapRenderScale;
        if(!bHasInk) {Result.InkTop=Top;Result.InkBottom=Bottom;bHasInk=true;}
        else {Result.InkTop=FMath::Min(Result.InkTop,Top);Result.InkBottom=FMath::Max(Result.InkBottom,Bottom);}
    }
    if(!bHasInk) Result.InkBottom=Result.Size.Y;
    return Result;
}
