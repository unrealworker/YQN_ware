#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GHSWarehouseRoofComponent.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;

/** One clock governs the rendered cut and the interior interaction lock. */
struct TEST_API FGHSWarehouseRoofTransition
{
    static constexpr float Duration = .5f;
    void Open() { if (Phase == 0) Phase = 1; }
    void Restore() { Phase=0; Elapsed=0.f; }
    void Advance(float DeltaSeconds)
    {
        if (Phase!=1 || !FMath::IsFinite(DeltaSeconds) || DeltaSeconds<=0.f) return;
        Elapsed=FMath::Min(Duration,Elapsed+DeltaSeconds);
        if (Elapsed>=Duration) Phase=2;
    }
    bool IsClosed() const { return Phase==0; }
    bool IsOpening() const { return Phase==1; }
    bool IsOpen() const { return Phase==2; }
    float Progress() const { return Elapsed/Duration; }
private:
    uint8 Phase=0;
    float Elapsed=0.f;
};

/** The architecture roof has no equipment identity and never changes its saved asset. */
UCLASS(ClassGroup=(GHS), meta=(BlueprintSpawnableComponent))
class TEST_API UGHSWarehouseRoofComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UGHSWarehouseRoofComponent();
    virtual void TickComponent(float DeltaTime,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction) override;

    UFUNCTION(BlueprintCallable, Category="Warehouse Roof")
    bool OpenRoof();
    UFUNCTION(BlueprintCallable, Category="Warehouse Roof")
    void RestoreRoof();
    /** Hides shell only after the roof opens; latest target wins during dissolve. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Roof") void SetBuildingVisible(bool bVisible);
    UFUNCTION(BlueprintPure, Category="Warehouse Roof") bool IsBuildingVisible() const { return bBuildingVisible; }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool IsInteriorAvailable() const { return !HasRoof() || Transition.IsOpen(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool IsRoofClosed() const { return HasRoof() && Transition.IsClosed(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool IsOpening() const { return HasRoof() && Transition.IsOpening(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool HasRoof() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    float GetOpenProgress() const { return Transition.Progress(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    FVector GetPOIWorldLocation() const;

    bool HitRoofRay(const FVector& Origin,const FVector& Direction) const;
    /** Called at BeginPlay; also supports headless world fixtures. */
    void InitializeRoof();
    static bool RayHitsRoofFootprint(const FVector& Origin,const FVector& Direction,const FTransform& RoofTransform);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    void UpdateShellVisibility();
    struct FShellActor { TWeakObjectPtr<AActor> Actor; bool bOriginallyHidden=false; };
    TArray<FShellActor> ShellActors;
    bool bShellInitialized=false,bBuildingVisible=true;
    void UpdateDissolveMaterials();
    void RestoreSourceMaterials();
    UPROPERTY(Transient) TObjectPtr<AActor> RoofActor;
    UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> RoofMesh;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInterface>> SourceMaterials;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> DissolveInstances;
    /** Hard asset references keep all six current source-shading variants in cooked builds. */
    UPROPERTY() TArray<TObjectPtr<UMaterialInterface>> DissolveTemplates;
    FGHSWarehouseRoofTransition Transition;
};
