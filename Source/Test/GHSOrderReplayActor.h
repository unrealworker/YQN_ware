#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GHSOrderReplaySimulation.h"
#include "GHSOrderReplayActor.generated.h"

class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UDecalComponent;

/** Isolated, fixed-size replay presentation. The HUD exclusively owns its clock. */
UCLASS(NotBlueprintable)
class TEST_API AGHSOrderReplayActor : public AActor
{
    GENERATED_BODY()
public:
    AGHSOrderReplayActor();
    bool InitializeReplay();
    void EvaluateAt(double Time);
    void SetPlaybackEndTime(double EndTime);
    void SetTrailMode(const FString& Mode,const FString& SelectedId);
    FString GetSnapshotJson() const;
    FString GetEventsJson(double WindowStart,double WindowEnd,int32 Limit=256) const;
    FString GetSourceInstancesJson() const;
    bool ResolveDevice(const FString& Id,FVector& Location,FRotator& Rotation,FVector& Extent) const;
    bool PickRay(const FVector& Origin,const FVector& Direction,FString& Id) const;
    const FString& GetError() const { return Error; }
    double GetCycleDuration() const { return Simulation.CycleDuration; }
    const GHSReplay::Simulation& GetSimulation() const { return Simulation; }
private:
    bool LoadData();
    UStaticMeshComponent* AddMesh(const FString& Name,const FString& Path);
    void UpdateTrails();
    GHSReplay::Simulation Simulation;
    std::array<GHSReplay::TrailPlan,GHSReplay::ForkCount> TrailPlans;
    std::array<GHSReplay::TrailState,GHSReplay::ForkCount> TrailStates;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Bodies;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Carriages;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Masts;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> DoorLeft;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> DoorRight;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Fixtures;
    UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> Trails;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> TrailMaterials;
    UPROPERTY(Transient) TArray<TObjectPtr<UDecalComponent>> GroundRipples;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> RippleMaterials;
    FString Error,SourceInstancesJson,TrailMode=TEXT("all"),SelectedId;
    double CurrentTime=0,PlaybackEndTime=-1.;
    bool bReady=false;
};
