#include "GHSWarehouseClock.h"

#include "Internationalization/Internationalization.h"
#include "Internationalization/Text.h"

FGHSWarehouseClock FGHSWarehouseClock::Format(const FDateTime& Utc)
{
    const FCulturePtr Culture = FInternationalization::Get().GetCulture(TEXT("en-US"));
    const FString TimeZone(TEXT("America/Los_Angeles"));
    const auto Part = [&Utc, &Culture, &TimeZone](const TCHAR* Pattern) -> FString
    {
        return FText::AsDateTime(Utc, Pattern, TimeZone, Culture).ToString();
    };

    FGHSWarehouseClock Result;
    Result.TimeText = Part(TEXT("%H:%M:%S"));

    // UE converts the custom pattern into an ICU skeleton, whose field order
    // and separators follow the culture. Assemble the fixed numeric date here.
    const int32 Year = FCString::Atoi(*Part(TEXT("%Y")));
    const int32 Month = FCString::Atoi(*Part(TEXT("%m")));
    const int32 Day = FCString::Atoi(*Part(TEXT("%d")));
    const FString ZoneName = Part(TEXT("z"));
    const FString Offset = Part(TEXT("xxx")).Replace(TEXT("-"), TEXT("−"));
    Result.DateText = FString::Printf(TEXT("%04d.%02d.%02d · %s (UTC%s)"), Year, Month, Day, *ZoneName, *Offset);
    Result.CachedUtcSecond = Utc.GetTicks() / ETimespan::TicksPerSecond;
    return Result;
}

bool FGHSWarehouseClock::Refresh(const FDateTime& Utc)
{
    if (CachedUtcSecond == Utc.GetTicks() / ETimespan::TicksPerSecond)
    {
        return false;
    }

    *this = Format(Utc);
    return true;
}
