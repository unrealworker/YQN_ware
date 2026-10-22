#if WITH_DEV_AUTOMATION_TESTS

#include "../GHSWarehouseClock.h"
#include "Internationalization/Internationalization.h"
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"

namespace GHSWarehouseClockTests
{
    constexpr uint32 Flags = EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::ProductFilter;

    struct FSample
    {
        const TCHAR* Label;
        FDateTime Utc;
        const TCHAR* Time;
        const TCHAR* Date;
    };

    void CheckSamples(FAutomationTestBase& Test, const TArray<FSample>& Samples)
    {
        for (const FSample& Sample : Samples)
        {
            const FGHSWarehouseClock Clock = FGHSWarehouseClock::Format(Sample.Utc);
            Test.TestEqual(FString::Printf(TEXT("%s time"), Sample.Label), Clock.TimeText, FString(Sample.Time));
            Test.TestEqual(FString::Printf(TEXT("%s date and zone"), Sample.Label), Clock.DateText, FString(Sample.Date));
        }
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseClockLocalDate,
    "GHS.WarehouseClock.LocalDateAnd24HourTime", GHSWarehouseClockTests::Flags)
bool FGHSWarehouseClockLocalDate::RunTest(const FString& Parameters)
{
    // A fixed UTC offset, UTC calendar date, 12-hour clock, or unpadded fields
    // each produce different visible output in at least one of these fixtures.
    GHSWarehouseClockTests::CheckSamples(*this, {
        { TEXT("Winter"), FDateTime(2026, 1, 15, 20, 4, 5), TEXT("12:04:05"), TEXT("2026.01.15 · PST (UTC−08:00)") },
        { TEXT("Summer"), FDateTime(2026, 7, 15, 20, 4, 5), TEXT("13:04:05"), TEXT("2026.07.15 · PDT (UTC−07:00)") },
        { TEXT("UTC year already advanced"), FDateTime(2026, 1, 1, 0, 1, 2), TEXT("16:01:02"), TEXT("2025.12.31 · PST (UTC−08:00)") },
        { TEXT("Before local winter midnight"), FDateTime(2026, 1, 15, 7, 59, 59), TEXT("23:59:59"), TEXT("2026.01.14 · PST (UTC−08:00)") },
        { TEXT("Local winter midnight"), FDateTime(2026, 1, 15, 8, 0, 0), TEXT("00:00:00"), TEXT("2026.01.15 · PST (UTC−08:00)") },
        { TEXT("Local summer midnight"), FDateTime(2026, 7, 15, 7, 0, 0), TEXT("00:00:00"), TEXT("2026.07.15 · PDT (UTC−07:00)") }
    });
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseClockDaylightSaving,
    "GHS.WarehouseClock.DaylightSavingBoundaries2026", GHSWarehouseClockTests::Flags)
bool FGHSWarehouseClockDaylightSaving::RunTest(const FString& Parameters)
{
    // The spring gap and fall overlap must change the displayed zone and UTC
    // offset at the same instant as the local clock.
    GHSWarehouseClockTests::CheckSamples(*this, {
        { TEXT("Before spring jump"), FDateTime(2026, 3, 8, 9, 59, 59), TEXT("01:59:59"), TEXT("2026.03.08 · PST (UTC−08:00)") },
        { TEXT("After spring jump"), FDateTime(2026, 3, 8, 10, 0, 0), TEXT("03:00:00"), TEXT("2026.03.08 · PDT (UTC−07:00)") },
        { TEXT("Before fall overlap"), FDateTime(2026, 11, 1, 8, 59, 59), TEXT("01:59:59"), TEXT("2026.11.01 · PDT (UTC−07:00)") },
        { TEXT("After fall overlap"), FDateTime(2026, 11, 1, 9, 0, 0), TEXT("01:00:00"), TEXT("2026.11.01 · PST (UTC−08:00)") }
    });
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseClockRefresh,
    "GHS.WarehouseClock.RefreshOncePerUtcSecondAndAfterClockCorrection", GHSWarehouseClockTests::Flags)
bool FGHSWarehouseClockRefresh::RunTest(const FString& Parameters)
{
    FGHSWarehouseClock Clock;
    TestTrue(TEXT("The first frame initializes the display"), Clock.Refresh(FDateTime(2026, 7, 15, 20, 4, 5, 100)));
    TestEqual(TEXT("Initial display uses warehouse time"), Clock.TimeText, FString(TEXT("13:04:05")));
    TestFalse(TEXT("Another frame within the same UTC second skips formatting"), Clock.Refresh(FDateTime(2026, 7, 15, 20, 4, 5, 999)));
    TestEqual(TEXT("Skipped formatting preserves display"), Clock.TimeText, FString(TEXT("13:04:05")));
    TestTrue(TEXT("The next UTC second updates the display"), Clock.Refresh(FDateTime(2026, 7, 15, 20, 4, 6)));
    TestEqual(TEXT("The second advances"), Clock.TimeText, FString(TEXT("13:04:06")));
    TestTrue(TEXT("A backward system-clock correction also updates"), Clock.Refresh(FDateTime(2026, 7, 15, 20, 4, 4)));
    TestEqual(TEXT("The corrected time is visible immediately"), Clock.TimeText, FString(TEXT("13:04:04")));
    TestFalse(TEXT("The corrected second is cached"), Clock.Refresh(FDateTime(2026, 7, 15, 20, 4, 4, 500)));

    FGHSWarehouseClock AtMidnight = FGHSWarehouseClock::Format(FDateTime(2026, 7, 15, 6, 59, 59));
    TestTrue(TEXT("Crossing local midnight refreshes"), AtMidnight.Refresh(FDateTime(2026, 7, 15, 7, 0, 0)));
    TestEqual(TEXT("Both time and date refresh at local midnight"), AtMidnight.DateText, FString(TEXT("2026.07.15 · PDT (UTC−07:00)")));
    TestEqual(TEXT("Midnight uses zero instead of 24"), AtMidnight.TimeText, FString(TEXT("00:00:00")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSWarehouseClockCulture,
    "GHS.WarehouseClock.IndependentOfCurrentCulture", GHSWarehouseClockTests::Flags)
bool FGHSWarehouseClockCulture::RunTest(const FString& Parameters)
{
    FInternationalization& I18N = FInternationalization::Get();
    FInternationalization::FCultureStateSnapshot OriginalCulture;
    I18N.BackupCultureState(OriginalCulture);
    ON_SCOPE_EXIT { I18N.RestoreCultureState(OriginalCulture); };

    if (!TestTrue(TEXT("Chinese culture is available for the locale-independence test"), I18N.SetCurrentCulture(TEXT("zh-CN"))))
    {
        return false;
    }
    GHSWarehouseClockTests::CheckSamples(*this, {
        { TEXT("Chinese UI still shows the specified warehouse format"), FDateTime(2026, 7, 15, 20, 4, 5), TEXT("13:04:05"), TEXT("2026.07.15 · PDT (UTC−07:00)") }
    });
    return true;
}

#endif
