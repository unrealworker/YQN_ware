#pragma once
#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Widget.h"
#include "Components/EditableTextBox.h"
#include "GHSTwinLayout.h"
#include "GHSTwinSceneData.h"
#include "GHSTwinHUDWidget.generated.h"

class SWebBrowser;
class UCanvasPanelSlot;

UCLASS()
class TEST_API UGHSTwinBrowser : public UWidget
{
    GENERATED_BODY()
public:
    void Bind(UObject* Target);
    void Evaluate(const FString& Script);
    virtual void ReleaseSlateResources(bool bReleaseChildren) override;
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
private:
    TSharedPtr<SWebBrowser> Browser;
};

UCLASS()
class TEST_API UGHSTwinHUDWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") void Command(const FString& Json);
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FString GetSnapshot() const;
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") bool SelectObject(const FString& Id, bool bFocus = true);
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") void ClearSelection();
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") bool HandleSceneClick(FVector2D Position);
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") bool IsScenePoint(FVector2D Position) const;
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") void Navigate(const FString& Page);
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetPanelPosition() const { return Layout.PanelPosition; }
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetPanelSize() const { return Layout.PanelSize; }
    UPROPERTY(BlueprintReadOnly, Category="Warehouse Twin") FString SelectedId;
    UPROPERTY(BlueprintReadOnly, Category="Warehouse Twin") bool bBrowserReady = false;
    UPROPERTY(BlueprintReadOnly, Category="Warehouse Twin") FString LastBrowserReport;
    UFUNCTION(BlueprintCallable, Category="Warehouse Twin") bool HandleChromeClick(FVector2D Position);
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") float GetPanelTransitionProgress() const { return PanelVisibilityProgress; }
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetPanelVisualPosition() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetPanelVisualSize() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") float GetPanelOpacity() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FString GetPOIReport() const;
    UFUNCTION() void SearchCommitted(const FText& Text, ETextCommit::Type Method);
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual void NativeConstruct() override;
    virtual void NativeDestruct() override;
    virtual void NativeTick(const FGeometry& Geometry, float DeltaSeconds) override;
    virtual int32 NativePaint(const FPaintArgs&, const FGeometry&, const FSlateRect&, FSlateWindowElementList&, int32, const FWidgetStyle&, bool) const override;
private:
    void PushSnapshot(bool bExplicitSelection=false);
    void Focus(const FString& Id);
    void Overview();
    void FocusRegion(const FString& Region);
    UPROPERTY(Transient) TObjectPtr<UGHSTwinBrowser> Panel;
    UPROPERTY(Transient) TObjectPtr<UCanvasPanelSlot> PanelSlot;
    UPROPERTY(Transient) TObjectPtr<UEditableTextBox> SearchBox;
    UPROPERTY(Transient) TObjectPtr<UCanvasPanelSlot> SearchSlot;
    FGHSTwinSceneData SceneData;
    FGHSTwinLayout Layout;
    FVector2D ViewSize = FVector2D(1920,1080);
    double NextRefresh = 0;
    bool bPanelCollapsed = false, bShowPOIs = true, bEquipment = true, bRacks = true;
    bool bInitialViewPending = true;
    float PanelVisibilityProgress = 1.f;
    FGHSTwinPanelMotion PanelMotion;
    FString Density = TEXT("auto");
    FString PointFilter = TEXT("all");
    FString ActiveRegionId;
    struct FLabel { FString Id, Text, Kind, Status; FVector2D Position; FVector2D Anchor; FVector2D Size; bool bAlert=false; bool bSelected=false; bool bHovered=false; float Opacity=1; };
    TArray<FLabel> Labels;
    TMap<FString,FVector2D> PreviousPositions;
    TMap<FString,float> LabelAges;
};
