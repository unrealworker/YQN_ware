#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MPRSorterSimulation.h"
#include "MPRSorterSimulationActor.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMPRSorterHUDWidget;

/** MPR-only, source-fitted demonstration of a circulating lift sorter. */
UCLASS(NotBlueprintable)
class TEST_API AMPRSorterSimulationActor : public AActor
{
    GENERATED_BODY()
public:
    AMPRSorterSimulationActor();
    virtual void Tick(float DeltaSeconds) override;
#if WITH_EDITOR
    virtual void OnConstruction(const FTransform& Transform) override;
#endif
    UPROPERTY(EditAnywhere, Category="MPR Sorter") FString LayoutJson;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UStaticMesh> TowerMesh;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UStaticMesh> TrayMesh;
    // Hard references keep all runtime cart variants available when cooking.
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TArray<TObjectPtr<UStaticMesh>> CartMeshes;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> ParcelMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> ActiveMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> FullMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<UMaterialInterface> WorkerSkinMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<UMaterialInterface> WorkerClothMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<UMaterialInterface> WorkerHelmetMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<UMaterialInterface> WorkerBootMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") bool bAutoStart=true;
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetSimulationPlaying(bool bPlaying);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void ResetSimulation();
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetSimulationRate(double Rate);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetAutomaticCollection(bool bEnabled);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void ClearFullBins();
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void FocusMachine(int32 Index);
    UFUNCTION(BlueprintPure, Category="MPR Sorter") FString GetSimulationReportJson() const;
    UFUNCTION(BlueprintCallable, Category="MPR Sorter|Diagnostics") bool AdvanceSimulationForDiagnostics(double Seconds);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter|Diagnostics") void SetAutomaticAdvanceForDiagnostics(bool bEnabled);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter|Diagnostics") void SetPanelVisible(bool bVisible);
    bool IsReady() const { return bReady; }
    bool IsSimulationPlaying() const;
    bool IsAutomaticCollection() const;
    double GetSimulationRate() const;
    int32 GetMachineCount() const { return Machines.Num(); }
    int32 GetSelectedMachineIndex() const { return SelectedMachine; }
    FString GetMachineTitle() const;
    FString GetStatusText() const;
    FString GetProgressText() const;
    FString GetCarrierText() const;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    friend class FMPRSorterLayoutValidation;
    struct FBinPoint { FVector Entry,Outlet,Drop; double RimZ=0; };
    struct FCartPoint
    {
        FString MeshPath;
        FVector Origin,BoundsMin,BoundsMax;
        double Retreat=65,OutboundEndX=0;
        int32 Side=0,FirstColumn=0,ColumnCount=0,ComponentIndex=INDEX_NONE,InstanceIndex=INDEX_NONE;
    };
    struct FMachine
    {
        FString Id,Profile;
        FTransform World;
        double Half=0,Radius=0,LoadFraction=0,InfeedSide=1;
        FVector Pickup,Entry,FeedStart;
        TArray<FBinPoint> Bins;
        TArray<FCartPoint> Carts;
        MPRSorter::Simulation Simulation;
        int32 BinOffset=0,FeedOffset=0,WorkerOffset=0;
        TArray<int32> CachedBinState;
    };
    bool LoadLayout();
    void UpdateInstances();
    void UpdateFocus();
    void AttachPanel();
    FVector CartOffset(const FMachine& Machine,int32 CartIndex) const;
    FVector FeedPoint(const FMachine& Machine,double Progress) const;
    FVector CarrierParcelPoint(const FMachine& Machine,const MPRSorter::Carrier& Carrier,FQuat& Turn) const;
    void UpdateWorker(int32 Index,const FMachine& Machine,const FVector& Feet,const FVector& LeftHand,
                      const FVector& RightHand,double Heading,double Step,bool bVisible);
    bool BuildCartInstances(bool bEditorPreview=false);
    void ClearCartInstances();
    bool AdvanceFleet(double WallSeconds);
    void ScheduleCartExchange();
    static FVector PointOnLoop(double Fraction,double Half,double Radius,double& Heading);
    UInstancedStaticMeshComponent* MakeInstances(const TCHAR* Name);
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Towers;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Trays;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Parcels;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> InfeedParcels;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> BinParcels;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> ActiveLights;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> FullLights;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> WorkerCloth;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> WorkerSkin;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> WorkerHelmet;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> WorkerBoots;
    UPROPERTY(Transient,DuplicateTransient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> RuntimeCartComponents;
    UPROPERTY(Transient) TObjectPtr<UMPRSorterHUDWidget> Panel;
    TArray<FMachine> Machines;
    FString Error;
    int32 SelectedMachine=0,PendingFocus=INDEX_NONE;
    int32 ExchangeOwner=INDEX_NONE,NextExchangeMachine=0;
    uint64 OwnerCompletedExchanges=0;
    bool bReady=false,bAutomaticAdvance=true;
};
