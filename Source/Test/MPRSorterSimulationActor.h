#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MPRSorterSimulation.h"
#include "MPRCentralDistribution.h"
#include "MPRCentralGeometry.h"
#include "MPRInstanceMotionHistory.h"
#include "MPRSorterSimulationActor.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMPRSorterHUDWidget;
class UMPRWorkerPoseComponent;
class USkeletalMesh;
class UAnimSequence;
class FJsonObject;
struct FMPRWorkerPoseInput;

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
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<USkeletalMesh> WorkerMesh;
    UPROPERTY(EditAnywhere, Category="MPR Sorter|Operators") TObjectPtr<UAnimSequence> WorkerIdle;
    UPROPERTY(EditAnywhere, Category="MPR Sorter") bool bAutoStart=true;
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetSimulationPlaying(bool bPlaying);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void ResetSimulation();
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetSimulationRate(double Rate);
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetAutomaticCollection(bool bEnabled);
    // Disabling incoming work drains parcels but keeps the central loop running.
    UFUNCTION(BlueprintCallable, Category="MPR Sorter") void SetCentralFeedingEnabled(bool bEnabled);
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
    struct FFeedStation
    {
        FVector Feet,Drop;
        double Yaw=0,Distance01=0;
        int32 WorkerIndex=INDEX_NONE;
        bool bManual=true;
    };
    struct FDistributionBank
    {
        FString Id,Profile;
        MPRCentralGeometry::Bank Geometry;
        TArray<FFeedStation> Stations;
        TArray<int32> Targets;
        TArray<MPRCentralGeometry::Belt> Belts;
        MPRCentral::Simulation Simulation;
        int32 CarrierOffset=0;
    };
    bool LoadLayout();
    bool LoadCentralDistribution();
    void BuildCentralDistribution();
    void UpdateCentralDistribution();
    bool AdvanceCentralDistribution(double SimSeconds);
    void SuppressLegacySpines();
    FVector CentralParcelPoint(const FDistributionBank& Bank,const MPRCentral::Carrier& Carrier) const;
    double CentralLiftHeight(const MPRCentral::Carrier& Carrier) const;
    void AppendCentralReport(const TSharedPtr<FJsonObject>& Report) const;
    void UpdateInstances();
    void UpdateFocus();
    void AttachPanel();
    FVector CartOffset(const FMachine& Machine,int32 CartIndex) const;
    FVector FeedPoint(const FMachine& Machine,double Progress) const;
    FVector CarrierParcelPoint(const FMachine& Machine,const MPRSorter::Carrier& Carrier,FQuat& Turn) const;
    void UpdateWorker(int32 Index,const FMachine& Machine,const FMPRWorkerPoseInput& Input);
    bool BuildWorkers();
    void RefitCadWorktables();
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
    UPROPERTY(Transient,DuplicateTransient) TArray<TObjectPtr<UMPRWorkerPoseComponent>> RuntimeWorkers;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralMetal;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralWhite;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralBlue;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralBelt;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralColumns;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralTrays;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UInstancedStaticMeshComponent> CentralParcels;
    UPROPERTY(Transient) TObjectPtr<UMPRSorterHUDWidget> Panel;
    TArray<FMachine> Machines;
    TArray<FDistributionBank> DistributionBanks;
    FMPRInstanceMotionHistory CentralColumnHistory, CentralTrayHistory, CentralParcelHistory;
    TArray<int32> CadWorkerIndices;
    uint64 NextCentralParcelId=1;
    double FleetTimeRemainder=0;
    int32 SuppressedSpineInstances=0;
    int32 RefittedCadWorktables=0;
    int32 RefittedCadOperatorStations=0;
    FString Error;
    int32 SelectedMachine=0,PendingFocus=INDEX_NONE;
    int32 ExchangeOwner=INDEX_NONE,NextExchangeMachine=0;
    uint64 OwnerCompletedExchanges=0;
    bool bReady=false,bAutomaticAdvance=true;
};
