#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GHSWarehouseRegistry.h"
#include "GHSGlobeWarehouseMarkers.generated.h"

class UDecalComponent;

/** Geographic markers projected onto the rendered Earth surface, independent of browser timing. */
UCLASS(NotBlueprintable, Transient)
class TEST_API AGHSGlobeWarehouseMarkers : public AActor
{
    GENERATED_BODY()
public:
    AGHSGlobeWarehouseMarkers();
    void Initialize(AActor* GlobeRoot, float GlobeRadius, const TArray<FGHSGlobeWarehouse>& Warehouses);
    void SetSelectedWarehouse(const FString& WarehouseId);

private:
    UPROPERTY(Transient) TMap<FString, TObjectPtr<UDecalComponent>> Markers;
    FString SelectedId;
};
