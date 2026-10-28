#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "TimerManager.h"
#include "GHSStorageCapacityComponent.generated.h"

class UPrimitiveComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;

/** Matches the integer material permutation. The midpoint makes 0 and 1 exact. */
namespace GHSStorageCapacity
{
    TEST_API int32 SlotRank(int32 GlobalSlot, int32 TotalSlots);
    TEST_API bool IsSlotVisible(int32 GlobalSlot, int32 TotalSlots, float Capacity);
    TEST_API float ClampCapacity(float Value, float Previous);
}

/** Controls full-load HISM assets without changing instances or rebuilding their trees. */
UCLASS(ClassGroup=(GHS), meta=(BlueprintSpawnableComponent))
class TEST_API UGHSStorageCapacityComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UGHSStorageCapacityComponent();
    /** Idempotent setup; call after the map's storage components are registered. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Storage")
    bool InitializeForWorld();
    /** Values are fractions [0,1], NaN/Inf preserve the previous value. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Storage")
    void SetCapacity(float Rack, float Floor);
    UFUNCTION(BlueprintCallable, Category="Warehouse Storage")
    void SetStorageVisible(bool bVisible);
    /** World-space point; true for unrelated components. Hidden cargo never hits. */
    UFUNCTION(BlueprintPure, Category="Warehouse Storage")
    bool IsStorageHitVisible(UPrimitiveComponent* Component, int32 InstanceIndex, const FVector& WorldPoint) const;
    UFUNCTION(BlueprintPure, Category="Warehouse Storage")
    FString GetReportJson() const;
    float GetRackCapacity() const { return RackCapacity; }
    float GetFloorCapacity() const { return FloorCapacity; }
    bool IsStorageVisible() const { return bStorageVisible; }

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    struct FSlot { FBox Bounds; int32 Index=0; };
    struct FGroup
    {
        TWeakObjectPtr<UInstancedStaticMeshComponent> Component;
        TArray<FSlot> Slots;
        int32 BaseSlot=0, SlotsPerInstance=0, InstanceCount=0;
        bool bRack=false;
        bool bRestoreAlwaysShadowInvalidation=false, bShadowCacheRefreshing=false;
    };
    void BeginCapacityShadowUpdate(bool bRackChanged, bool bFloorChanged);
    void RestoreCachedShadows();
    TArray<FGroup> Groups;
    TMap<TWeakObjectPtr<UPrimitiveComponent>,int32> GroupByComponent;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> RackMaterials;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> FloorMaterials;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInterface>> SourceMaterials;
    TArray<TPair<TWeakObjectPtr<UInstancedStaticMeshComponent>,int32>> SourceMaterialSlots;
    float RackCapacity=.8f, FloorCapacity=1.f;
    int32 RackTotalSlots=0, FloorTotalSlots=0;
    uint64 InitializationScans=0, ParameterWrites=0, CapacityUpdates=0;
    uint64 ShadowCacheRefreshRequests=0;
    FTimerHandle ShadowCacheSettleTimer;
    bool bStorageVisible=true, bInitialized=false;
    FString InitializationError;
};
