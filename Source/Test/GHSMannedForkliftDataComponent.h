#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GHSMannedForkliftDataComponent.generated.h"

UENUM(BlueprintType)
enum class EGHSMannedForkliftStatus : uint8
{
    AwaitingData,
    Running,
    Idle,
    Warning,
    Fault,
    Offline
};

/** Staffed forklift identity and explicit telemetry; no powertrain or rated capacity is assumed. */
UCLASS(Blueprintable, ClassGroup=(GHS), meta=(BlueprintSpawnableComponent))
class TEST_API UGHSMannedForkliftDataComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UGHSMannedForkliftDataComponent();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Identity")
    FString ForkliftId;

    /** Metric tonnes; -1 means unknown, including fault and offline states. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    float LoadTonnes = -1.f;

    /** Kilometres per hour; -1 means unknown. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    float SpeedKmh = -1.f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    FString DriverId;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    FString Area;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    FString TaskId;
    /** Supplied task summary, warning or fault reason; never inferred from model geometry. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    FString Reason;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    EGHSMannedForkliftStatus Status = EGHSMannedForkliftStatus::AwaitingData;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    bool bIsDemoData = false;

    /** Game time of the accepted update, or -1 when no world/update is available. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    float LastUpdateSeconds = -1.f;
    /** Last connected update game time; a first offline sample keeps this unknown. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Manned Forklift|Telemetry")
    float LastOnlineSeconds = -1.f;

    /** NormalWarehouseMannedForklift + exactly one TwinId=GHN_MannedForklift_<positive integer>. */
    UFUNCTION(BlueprintCallable, Category="Manned Forklift")
    bool InitializeFromActorTags();
    UFUNCTION(BlueprintCallable, Category="Manned Forklift")
    bool InitializeIdentity(const FString& Id);

    /**
     * Load is tonnes and speed km/h, both finite and nonnegative for connected working states.
     * Fault/Offline/AwaitingData also accept (-1,-1) and always clear measurements.
     * Offline/AwaitingData additionally clear driver, area and task. Invalid updates are atomic.
     */
    UFUNCTION(BlueprintCallable, Category="Manned Forklift")
    bool SetTelemetry(float Load, float Speed, EGHSMannedForkliftStatus NewStatus,
        const FString& NewDriverId, const FString& NewArea, const FString& NewTaskId,
        const FString& NewReason, bool bDemoData = false);
    UFUNCTION(BlueprintPure, Category="Manned Forklift")
    bool HasTelemetry() const;
    /** Seeds explicitly marked design examples once; never replaces accepted live data. */
    UFUNCTION(BlueprintCallable, Category="Manned Forklift|Demo")
    bool ApplyDemoState(int32 Index);

    /** Runtime ownership cannot survive copying a component onto another vehicle. */
    bool IsIdentityBoundToOwner() const;
    bool HasAcceptedTelemetry() const { return bHasAcceptedUpdate; }
    /** Used only when a duplicated vehicle receives its own identity. */
    bool ResetForReassignedIdentity(const FString& Id);
private:
    UPROPERTY(Transient, DuplicateTransient)
    TWeakObjectPtr<AActor> IdentityOwner;
    UPROPERTY(Transient)
    bool bHasAcceptedUpdate = false;
};
