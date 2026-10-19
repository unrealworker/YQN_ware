#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GHSDockTruckDataComponent.generated.h"

UENUM(BlueprintType)
enum class EGHSDockTruckStatus : uint8
{
    AwaitingData,
    Docked,
    Loading,
    Warning,
    Fault,
    Offline
};

/** Runtime truck identity and explicitly supplied warehouse telemetry. */
UCLASS(Blueprintable, ClassGroup=(GHS), meta=(BlueprintSpawnableComponent))
class TEST_API UGHSDockTruckDataComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UGHSDockTruckDataComponent();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Identity")
    FString TruckId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Identity")
    FString DockId;

    /** -1 means unknown. Offline and AwaitingData always expose unknown counts. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    int32 LoadedPallets = -1;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    int32 TotalPallets = -1;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    FString OrderId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    EGHSDockTruckStatus Status = EGHSDockTruckStatus::AwaitingData;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    bool bIsDemoData = false;

    /** World game time of the latest accepted update; -1 before any update. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Dock Truck|Telemetry")
    float LastUpdateSeconds = -1.0f;

    /** Reads IndependentDockTruck, TwinId=GHS_DockTruck_<number>, and Dock=<number> tags. */
    UFUNCTION(BlueprintCallable, Category="Dock Truck")
    bool InitializeFromActorTags();

    /**
     * Rejects invalid updates without changing any stored field.
     * Counts must satisfy 0 <= Loaded <= Total and Total > 0. The pair (-1, -1)
     * is also accepted for Offline/AwaitingData; those states clear counts and order.
     */
    UFUNCTION(BlueprintCallable, Category="Dock Truck")
    bool SetTelemetry(int32 Loaded, int32 Total, EGHSDockTruckStatus NewStatus,
        const FString& NewOrderId, bool bDemoData = false);

    UFUNCTION(BlueprintPure, Category="Dock Truck")
    int32 GetRemainingPallets() const;

    UFUNCTION(BlueprintPure, Category="Dock Truck")
    float GetLoadingProgress() const;

    UFUNCTION(BlueprintPure, Category="Dock Truck")
    bool HasTelemetry() const;
};
