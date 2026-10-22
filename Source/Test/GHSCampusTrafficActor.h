#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GHSCampusTrafficSimulation.h"
#include "GHSCampusTrafficActor.generated.h"

class UInstancedStaticMeshComponent;

/** Decorative, non-interactive campus context: four ISMs, thirty-two fixed slots. */
UCLASS(NotBlueprintable)
class TEST_API AGHSCampusTrafficActor : public AActor
{
    GENERATED_BODY()
public:
    AGHSCampusTrafficActor();
    virtual void Tick(float DeltaSeconds) override;
    UFUNCTION(BlueprintPure, Category="Warehouse Traffic") FString GetTrafficReportJson() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Traffic") int32 GetActiveVehicleCount() const { return Simulation.ActiveCount(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Traffic") int32 GetVehicleCapacity() const { return GHSTraffic::Capacity; }
protected:
    virtual void BeginPlay() override;
private:
    struct FRoute
    {
        FString Id, Corridor;
        TArray<FVector> Points;
        TArray<double> Distances;
        double Length=0, MaxSpeed=0;
        FVector At(double Distance) const;
    };
    bool LoadRoutes();
    void UpdateInstances();
    UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> VehicleMeshes;
    TArray<FVector> MeshOffsets;
    TArray<FRoute> Routes;
    GHSTraffic::Simulation Simulation;
    int32 PeakActive=0;
    bool bReady=false;
};
