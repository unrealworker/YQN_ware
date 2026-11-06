#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GHSWarehouseRegistry.h"
#include "GHSGlobeWarehouseMarkers.generated.h"

class UStaticMeshComponent;

/** Cached geographic anchors on the Earth mesh. Rendering is owned by the native pixel overlay. */
UCLASS(NotBlueprintable, Transient)
class TEST_API AGHSGlobeWarehouseMarkers : public AActor
{
    GENERATED_BODY()
public:
    AGHSGlobeWarehouseMarkers();
    void Initialize(AActor* GlobeRoot, float GlobeRadius, const TArray<FGHSGlobeWarehouse>& Warehouses);
    UFUNCTION(BlueprintPure, Category="Globe") bool GetWorldAnchor(const FString& WarehouseId, FVector& OutPosition) const;
    UFUNCTION(BlueprintPure, Category="Globe") int32 GetAnchorCount() const { return LocalAnchors.Num(); }

private:
    TMap<FString, FVector> LocalAnchors;
    TWeakObjectPtr<UStaticMeshComponent> EarthMesh;
};
