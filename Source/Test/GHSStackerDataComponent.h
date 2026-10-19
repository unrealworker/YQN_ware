#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GHSStackerDataComponent.generated.h"

UENUM(BlueprintType)
enum class EGHSStackerStatus : uint8
{
    AwaitingData,
    Running,
    Idle,
    Warning,
    Fault,
    Offline
};

/** Electric stacker identity and explicitly supplied warehouse telemetry. */
UCLASS(Blueprintable, ClassGroup=(GHS), meta=(BlueprintSpawnableComponent))
class TEST_API UGHSStackerDataComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UGHSStackerDataComponent();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Identity")
    FString StackerId;

    /** -1 means unknown. Offline and AwaitingData clear both measurements. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry")
    float BatteryPercent = -1.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry", meta=(Units="cm"))
    float ForkHeightCm = -1.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry")
    FString TaskId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry")
    EGHSStackerStatus Status = EGHSStackerStatus::AwaitingData;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry")
    bool bIsDemoData = false;

    /** World game time of the latest accepted update; -1 without a game world. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stacker|Telemetry")
    float LastUpdateSeconds = -1.0f;

    /** Reads NormalWarehouseFloorStacker and a unique TwinId=GHN_FloorStacker_<number> tag. */
    UFUNCTION(BlueprintCallable, Category="Stacker")
    bool InitializeFromActorTags();

    /** Accepts STACKER-<positive integer>; normalizes display IDs to at least two digits. */
    UFUNCTION(BlueprintCallable, Category="Stacker")
    bool InitializeIdentity(const FString& Id);

    /**
     * Rejects invalid updates atomically. Battery must be finite and within 0..100;
     * fork height must be finite and nonnegative. Offline/AwaitingData also accept
     * (-1, -1) and always clear the measurements and task.
     */
    UFUNCTION(BlueprintCallable, Category="Stacker")
    bool SetTelemetry(float Battery, float ForkHeight, EGHSStackerStatus NewStatus,
        const FString& NewTaskId, bool bDemoData = false);

    UFUNCTION(BlueprintPure, Category="Stacker")
    bool HasTelemetry() const;

    /** Seeds one deterministic sample only before any telemetry has been accepted. */
    UFUNCTION(BlueprintCallable, Category="Stacker|Demo")
    bool ApplyDemoState(int32 Index);

private:
    // Independent of timestamps so explicit offline updates are protected even without a world.
    UPROPERTY(Transient)
    bool bHasAcceptedUpdate = false;
};
