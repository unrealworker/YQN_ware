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
    UPROPERTY(EditAnywhere, Category="MPR Sorter") FString LayoutJson;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UStaticMesh> TowerMesh;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UStaticMesh> TrayMesh;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> ParcelMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> ActiveMaterial;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") TObjectPtr<UMaterialInterface> FullMaterial;
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
    struct FMachine
    {
        FString Id,Profile;
        FTransform World;
        double Half=0,Radius=0;
        TArray<FBinPoint> Bins;
        MPRSorter::Simulation Simulation;
        int32 BinOffset=0;
        TArray<int32> CachedBinState;
    };
    bool LoadLayout();
    void UpdateInstances();
    void UpdateFocus();
    void AttachPanel();
    static FVector PointOnLoop(double Fraction,double Half,double Radius,double& Heading);
    UInstancedStaticMeshComponent* MakeInstances(const TCHAR* Name);
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Towers;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Trays;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> Parcels;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> BinParcels;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> ActiveLights;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> FullLights;
    UPROPERTY(Transient) TObjectPtr<UMPRSorterHUDWidget> Panel;
    TArray<FMachine> Machines;
    FString Error;
    int32 SelectedMachine=0,PendingFocus=INDEX_NONE;
    bool bReady=false,bAutomaticAdvance=true;
};
