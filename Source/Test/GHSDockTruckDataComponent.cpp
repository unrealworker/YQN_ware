#include "GHSDockTruckDataComponent.h"

#include "Engine/World.h"
#include "GameFramework/Actor.h"

namespace
{
    // Atoi would silently accept missing suffixes, trailing text, signs, and overflow.
    bool ParsePositiveIdentifier(const FString& Value, int32& OutNumber)
    {
        if (Value.IsEmpty()) return false;

        int32 Number = 0;
        for (const TCHAR Character : Value)
        {
            if (Character < TEXT('0') || Character > TEXT('9')) return false;
            const int32 Digit = Character - TEXT('0');
            if (Number > (MAX_int32 - Digit) / 10) return false;
            Number = Number * 10 + Digit;
        }
        if (Number == 0) return false;
        OutNumber = Number;
        return true;
    }

    bool IsOperationalStatus(EGHSDockTruckStatus Status)
    {
        return Status == EGHSDockTruckStatus::Docked
            || Status == EGHSDockTruckStatus::Loading
            || Status == EGHSDockTruckStatus::Warning
            || Status == EGHSDockTruckStatus::Fault;
    }

    bool AreCountsValid(int32 Loaded, int32 Total)
    {
        return Total > 0 && Loaded >= 0 && Loaded <= Total;
    }
}

UGHSDockTruckDataComponent::UGHSDockTruckDataComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

bool UGHSDockTruckDataComponent::InitializeFromActorTags()
{
    const AActor* Owner = GetOwner();
    if (!IsValid(Owner) || !Owner->ActorHasTag(TEXT("IndependentDockTruck"))) return false;

    FString TwinIdValue;
    FString DockValue;
    bool bFoundTwinId = false;
    bool bFoundDock = false;
    for (const FName Tag : Owner->Tags)
    {
        const FString Value = Tag.ToString();
        if (Value.StartsWith(TEXT("TwinId="), ESearchCase::CaseSensitive))
        {
            if (bFoundTwinId) return false;
            bFoundTwinId = true;
            TwinIdValue = Value.Mid(7);
        }
        else if (Value.StartsWith(TEXT("Dock="), ESearchCase::CaseSensitive))
        {
            if (bFoundDock) return false;
            bFoundDock = true;
            DockValue = Value.Mid(5);
        }
    }

    int32 TruckNumber = 0;
    int32 DockNumber = 0;
    if (!bFoundTwinId || !bFoundDock
        || !TwinIdValue.RemoveFromStart(TEXT("GHS_DockTruck_"), ESearchCase::CaseSensitive)
        || !ParsePositiveIdentifier(TwinIdValue, TruckNumber)
        || !ParsePositiveIdentifier(DockValue, DockNumber))
    {
        return false;
    }

    TruckId = FString::Printf(TEXT("TRUCK-%03d"), TruckNumber);
    DockId = FString::Printf(TEXT("DOCK-%02d"), DockNumber);
    return true;
}

bool UGHSDockTruckDataComponent::SetTelemetry(int32 Loaded, int32 Total,
    EGHSDockTruckStatus NewStatus, const FString& NewOrderId, bool bDemoData)
{
    const bool bUnavailable = NewStatus == EGHSDockTruckStatus::AwaitingData
        || NewStatus == EGHSDockTruckStatus::Offline;
    if (!bUnavailable && !IsOperationalStatus(NewStatus)) return false;

    const bool bUnknownCounts = Loaded == -1 && Total == -1;
    if (!AreCountsValid(Loaded, Total) && !(bUnavailable && bUnknownCounts)) return false;

    LoadedPallets = bUnavailable ? -1 : Loaded;
    TotalPallets = bUnavailable ? -1 : Total;
    OrderId = bUnavailable ? FString() : NewOrderId;
    Status = NewStatus;
    bIsDemoData = bDemoData;
    const UWorld* World = GetWorld();
    LastUpdateSeconds = World ? World->GetTimeSeconds() : -1.0f;
    return true;
}

int32 UGHSDockTruckDataComponent::GetRemainingPallets() const
{
    return HasTelemetry() ? TotalPallets - LoadedPallets : -1;
}

float UGHSDockTruckDataComponent::GetLoadingProgress() const
{
    return HasTelemetry() ? static_cast<float>(LoadedPallets) / static_cast<float>(TotalPallets) : 0.0f;
}

bool UGHSDockTruckDataComponent::HasTelemetry() const
{
    return IsOperationalStatus(Status) && AreCountsValid(LoadedPallets, TotalPallets);
}
