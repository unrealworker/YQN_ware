#include "GHSStackerDataComponent.h"

#include "Engine/World.h"
#include "GameFramework/Actor.h"

namespace
{
    bool ParseStackerIdentifier(const FString& Value, int32& OutNumber)
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

    bool IsAvailableStatus(EGHSStackerStatus Status)
    {
        return Status == EGHSStackerStatus::Running || Status == EGHSStackerStatus::Idle
            || Status == EGHSStackerStatus::Warning || Status == EGHSStackerStatus::Fault;
    }

    bool AreMeasurementsValid(float Battery, float Height)
    {
        return FMath::IsFinite(Battery) && FMath::IsFinite(Height)
            && Battery >= 0.0f && Battery <= 100.0f && Height >= 0.0f;
    }
}

UGHSStackerDataComponent::UGHSStackerDataComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

bool UGHSStackerDataComponent::InitializeFromActorTags()
{
    const AActor* Owner = GetOwner();
    if (!IsValid(Owner) || !Owner->ActorHasTag(TEXT("NormalWarehouseFloorStacker"))) return false;

    FString TwinId;
    bool bFoundIdentity = false;
    for (const FName Tag : Owner->Tags)
    {
        const FString Value = Tag.ToString();
        if (!Value.StartsWith(TEXT("TwinId="), ESearchCase::CaseSensitive)) continue;
        if (bFoundIdentity) return false;
        bFoundIdentity = true;
        TwinId = Value.Mid(7);
    }
    if (!bFoundIdentity || !TwinId.RemoveFromStart(TEXT("GHN_FloorStacker_"), ESearchCase::CaseSensitive)) return false;
    return InitializeIdentity(TEXT("STACKER-") + TwinId);
}

bool UGHSStackerDataComponent::InitializeIdentity(const FString& Id)
{
    FString NumberText = Id;
    int32 Number = 0;
    if (!NumberText.RemoveFromStart(TEXT("STACKER-"), ESearchCase::CaseSensitive)
        || !ParseStackerIdentifier(NumberText, Number)) return false;
    StackerId = FString::Printf(TEXT("STACKER-%02d"), Number);
    return true;
}

bool UGHSStackerDataComponent::SetTelemetry(float Battery, float ForkHeight,
    EGHSStackerStatus NewStatus, const FString& NewTaskId, bool bDemoData)
{
    // Reject non-finite values before comparing against the unknown sentinel.
    // Fast floating-point builds may otherwise treat an unordered NaN compare
    // like equality and accept it as an unavailable measurement pair.
    if (!FMath::IsFinite(Battery) || !FMath::IsFinite(ForkHeight)) return false;
    const bool bUnavailable = NewStatus == EGHSStackerStatus::AwaitingData || NewStatus == EGHSStackerStatus::Offline;
    if (!bUnavailable && !IsAvailableStatus(NewStatus)) return false;
    const bool bUnknownMeasurements = Battery == -1.0f && ForkHeight == -1.0f;
    if (!AreMeasurementsValid(Battery, ForkHeight) && !(bUnavailable && bUnknownMeasurements)) return false;

    BatteryPercent = bUnavailable ? -1.0f : Battery;
    ForkHeightCm = bUnavailable ? -1.0f : ForkHeight;
    TaskId = bUnavailable ? FString() : NewTaskId;
    Status = NewStatus;
    bIsDemoData = bDemoData;
    const UWorld* World = GetWorld();
    LastUpdateSeconds = World ? World->GetTimeSeconds() : -1.0f;
    bHasAcceptedUpdate = true;
    return true;
}

bool UGHSStackerDataComponent::HasTelemetry() const
{
    return IsAvailableStatus(Status) && AreMeasurementsValid(BatteryPercent, ForkHeightCm);
}

bool UGHSStackerDataComponent::ApplyDemoState(int32 Index)
{
    if (Index < 0 || bHasAcceptedUpdate) return false;
    struct FDemoSample { EGHSStackerStatus State; float Battery; float Height; const TCHAR* Task; };
    static const FDemoSample Samples[] = {
        {EGHSStackerStatus::Running, 82, 180, TEXT("T-0301")},
        {EGHSStackerStatus::Idle, 96, 0, TEXT("")},
        {EGHSStackerStatus::Warning, 18, 90, TEXT("T-0303")},
        {EGHSStackerStatus::Fault, 43, 125, TEXT("T-0304")},
        {EGHSStackerStatus::Offline, -1, -1, TEXT("")},
        {EGHSStackerStatus::Running, 74, 210, TEXT("T-0306")},
        {EGHSStackerStatus::Idle, 89, 0, TEXT("")},
        {EGHSStackerStatus::Running, 67, 150, TEXT("T-0308")},
        {EGHSStackerStatus::Warning, 14, 60, TEXT("T-0309")},
        {EGHSStackerStatus::Idle, 91, 0, TEXT("")},
        {EGHSStackerStatus::Running, 58, 240, TEXT("T-0311")},
        {EGHSStackerStatus::Offline, -1, -1, TEXT("")}
    };
    const FDemoSample& Sample = Samples[Index % UE_ARRAY_COUNT(Samples)];
    return SetTelemetry(Sample.Battery, Sample.Height, Sample.State, Sample.Task, true);
}
