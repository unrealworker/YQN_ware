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
    static constexpr float ManualOpenDuration = .8f;
    static constexpr float FastOpenDuration = .5f;
    static constexpr float CloseDuration = .55f;

    void Open(bool bFast=false)
    {
        if(IsOpen()) return;
        if(Phase>=1.f) { State=EState::Open; return; }
        const float RequestedDuration=bFast?FastOpenDuration:ManualOpenDuration;
        if(IsOpening())
        {
            ActiveDuration=FMath::Min(ActiveDuration,RequestedDuration);
            return;
        }
        State=EState::Opening;
        ActiveDuration=RequestedDuration;
    }
    void Restore(bool bAnimate=true)
    {
        if(!bAnimate || Phase<=0.f)
        {
            State=EState::Closed;
            Phase=0.f;
            return;
        }
        if(IsClosed() || IsClosing()) return;
        State=EState::Closing;
        ActiveDuration=CloseDuration;
    }
    void Advance(float DeltaSeconds)
    {
        if(!IsTransitioning() || !FMath::IsFinite(DeltaSeconds) || DeltaSeconds<=0.f) return;
        const float Direction=IsOpening()?1.f:-1.f;
        Phase=FMath::Clamp(Phase+Direction*(DeltaSeconds/ActiveDuration),0.f,1.f);
        if(IsOpening() && Phase>=1.f) State=EState::Open;
        else if(IsClosing() && Phase<=0.f) State=EState::Closed;
    }
    bool IsClosed() const { return State==EState::Closed; }
    bool IsOpening() const { return State==EState::Opening; }
    bool IsOpen() const { return State==EState::Open; }
    bool IsClosing() const { return State==EState::Closing; }
    bool IsTransitioning() const { return IsOpening() || IsClosing(); }
    /** The same eased aperture is traversed in either direction, including reversals. */
    float Progress() const { return Phase*Phase*(3.f-2.f*Phase); }
    float GetPhase() const { return Phase; }
    float GetDuration() const { return ActiveDuration; }
private:
    enum class EState : uint8 { Closed,Opening,Open,Closing };
    EState State=EState::Closed;
    float Phase=0.f;
    float ActiveDuration=ManualOpenDuration;
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
    bool OpenRoof(bool bFast=false);
    UFUNCTION(BlueprintCallable, Category="Warehouse Roof")
    void RestoreRoof(bool bAnimate=true);
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
    bool IsClosing() const { return HasRoof() && Transition.IsClosing(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool IsTransitioning() const { return HasRoof() && Transition.IsTransitioning(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    bool HasRoof() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    float GetOpenProgress() const { return Transition.Progress(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    float GetTransitionPhase() const { return Transition.GetPhase(); }
    UFUNCTION(BlueprintPure, Category="Warehouse Roof")
    float GetTransitionDuration() const { return Transition.GetDuration(); }
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
    void ApplyDissolveMaterials();
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
