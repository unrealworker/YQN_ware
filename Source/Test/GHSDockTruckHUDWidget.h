#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "GHSTruckHUDLayout.h"
#include "GHSDockTruckHUDWidget.generated.h"

class UGHSDockTruckDataComponent;
class UGHSStackerDataComponent;
class UGHSMannedForkliftDataComponent;

/** Current visual geometry for integrations such as keyboard navigation. */
USTRUCT(BlueprintType)
struct FGHSTruckHUDLabelInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FString Key;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") TArray<FString> TruckIds;
    UPROPERTY(BlueprintReadOnly, Category="Warehouse HUD") TArray<FString> EquipmentIds;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D Position = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D Size = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") float Opacity = 0;
};

/** Screen-space truck labels. Data stays on the trucks; selection stays local to this player. */
UCLASS()
class TEST_API UGHSDockTruckHUDWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") int32 GetRegisteredTruckCount() const;
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") int32 GetRegisteredStackerCount() const;
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") int32 GetRegisteredMannedForkliftCount() const;
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") int32 GetRegisteredEquipmentCount() const;
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") UGHSStackerDataComponent* GetStackerData(const FString& StackerId) const;
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") UGHSMannedForkliftDataComponent* GetMannedForkliftData(const FString& ForkliftId) const;
    UFUNCTION(BlueprintCallable, Category="Warehouse HUD") bool SelectEquipmentById(const FString& EquipmentId);
    UFUNCTION(BlueprintPure, Category="Warehouse HUD") FString GetSelectedEquipmentId() const;
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") int32 GetVisibleLabelCount() const;
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") UGHSDockTruckDataComponent* GetTruckData(const FString& TruckId) const;
    UFUNCTION(BlueprintCallable, Category="Dock Truck HUD") bool SelectTruckById(const FString& TruckId);
    UFUNCTION(BlueprintCallable, Category="Dock Truck HUD") void ClearSelection();
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") FString GetSelectedTruckId() const;
    /** Widget-local coordinates, already scaled for the current viewport. */
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") FVector2D GetVisibleLabelPosition(const FString& TruckId) const;
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") TArray<FGHSTruckHUDLabelInfo> GetVisibleLabels() const;
    UFUNCTION(BlueprintCallable, Category="Dock Truck HUD") bool ToggleCluster(const FString& Key);
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") TArray<FString> GetExpandedClusterMembers() const;
    UFUNCTION(BlueprintCallable, Category="Dock Truck HUD") bool SetClusterPage(int32 Page);
    UFUNCTION(BlueprintPure, Category="Dock Truck HUD") FVector2D GetMemberRowPosition(const FString& TruckId) const;
    UFUNCTION(BlueprintCallable, Category="Dock Truck HUD") bool HandlePointerClick(FVector2D LocalPosition);
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D DetailPosition = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D DetailSize = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") bool bDetailVisible = false;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") float DetailTransitionProgress = 0;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") bool bClusterListVisible = false;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D ClusterListPosition = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") FVector2D ClusterListSize = FVector2D::ZeroVector;
    UPROPERTY(BlueprintReadOnly, Category="Dock Truck HUD") float ClusterTransitionProgress = 0;
protected:
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry,
        const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId,
        const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
    virtual FReply NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
    virtual FReply NativeOnMouseButtonDoubleClick(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
private:
    struct FEquipmentData
    {
        AActor* Owner = nullptr;
        FString Id, Title, StatusText, Metric, LeftValue, RightValue, TaskId, Location;
        FString DriverId, Reason, ConnectionText;
        bool bStacker = false, bDemo = false, bAvailable = false, bOffline = false;
        bool bMannedForklift = false;
        int32 Severity = 0;
        FLinearColor StateColor;
        float Progress = 0;
    };
    bool ReadEquipment(const FString& Id, FEquipmentData& Out) const;
    FString GroupTitle(const TArray<FString>& Ids) const;
    struct FTruckLabel
    {
        FString Key;
        TArray<FString> TruckIds;
        FVector2D Anchor = FVector2D::ZeroVector;
        FVector2D Position = FVector2D::ZeroVector;
        FVector2D Size = FVector2D::ZeroVector;
        FVector2D StartPosition = FVector2D::ZeroVector;
        FVector2D StartSize = FVector2D::ZeroVector;
        FVector2D TargetPosition = FVector2D::ZeroVector;
        FVector2D TargetSize = FVector2D::ZeroVector;
        float Time = 0;
        float Opacity = 0;
        float StartOpacity = 0;
        bool bRetiring = false;
    };
    void DiscoverTrucks();
    const FTruckLabel* FindLabelForTruck(const FString& TruckId) const;
    void UpdateLabels(const TArray<GHSTruckHUDLayout::FGroup>& Groups, float DeltaSeconds);
    void UpdatePopups(FVector2D Canvas, float DeltaSeconds);
    void CloseCluster();
    GHSTruckHUDLayout::FClusterer Clusterer;
    TArray<TWeakObjectPtr<UGHSDockTruckDataComponent>> Trucks;
    TArray<TWeakObjectPtr<UGHSStackerDataComponent>> Stackers;
    TArray<TWeakObjectPtr<UGHSMannedForkliftDataComponent>> MannedForklifts;
    TArray<FTruckLabel> Labels;
    FString SelectedEquipment;
    FString DisplayedEquipment;
    TArray<FString> ExpandedMembers;
    FString ExpandedKey;
    int32 ClusterPage = 0;
    float DetailTime = 0;
    float ClusterTime = 0;
    float DetailZoom = 1;
    float ClusterZoom = 1;
    FVector2D DetailBasePosition = FVector2D::ZeroVector;
    FVector2D ClusterBasePosition = FVector2D::ZeroVector;
    FVector2D LastCanvas = FVector2D::ZeroVector;
    bool bDetailPlacementPending = true;
    bool bDetailAbove = true;
    bool bClusterPlacementPending = true;
    bool bClusterAbove = false;
    float DiscoveryCountdown = 0;
    float DrawScale = 1;
};
