#pragma once
#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Widget.h"
#include "Components/EditableTextBox.h"
#include "GHSTwinLayout.h"
#include "GHSTwinSceneData.h"
#include "GHSTwinSearchLayout.h"
#include "GHSTwinTypography.h"
#include "GHSTwinHUDWidget.generated.h"

class SWebBrowser;
class UCanvasPanelSlot;
class SGHSTwinEditableText;
class UGHSTwinHUDWidget;

/** Native IME context remains owned by Slate; composition is never queried prematurely. */
UCLASS()
class TEST_API UGHSTwinSearchInput : public UWidget
{
    GENERATED_BODY()
public:
    void Bind(UGHSTwinHUDWidget* Owner);
    void SetText(const FString& Value);
    bool IsComposing() const;
    bool HasInputFocus() const;
    virtual void ReleaseSlateResources(bool bReleaseChildren) override;
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
private:
    TWeakObjectPtr<UGHSTwinHUDWidget> SearchOwner;
    TSharedPtr<SGHSTwinEditableText> Editor;
};

/** Candidate work is periodic; visible-point projection remains per frame. */
struct FGHSTwinPOIRefreshPolicy
{
    bool Consume(double Now,uint64 CurrentRevision,bool bCurrentFar)
    {
        if(!bDirty && Now>=LastRefresh && Now<NextRefresh && Revision==CurrentRevision && bFar==bCurrentFar) return false;
        bDirty=false;Revision=CurrentRevision;bFar=bCurrentFar;LastRefresh=Now;NextRefresh=Now+.1;return true;
    }
    void Invalidate() { bDirty=true; }
private:
    double NextRefresh=0,LastRefresh=-1;
    uint64 Revision=MAX_uint64;
    bool bFar=false,bDirty=true;
};
namespace GHSTwinHUDPerformance
{
    inline bool ShouldRefreshBrowser(bool bCollapsed,float Progress) { return !bCollapsed || Progress>0.f; }
}

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
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetSceneControlsPosition() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetSceneSearchPosition() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FVector2D GetSceneSearchSize() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") bool IsSceneSearchVisible() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") float GetPanelOpacity() const;
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FString GetPOIReport() const;
    UFUNCTION() void SearchCommitted(const FText& Text, ETextCommit::Type Method);
    void SearchChanged(const FText& Text);
    void SetSearchOpen(bool bOpen);
    bool HandleSearchKey(FKey Key);
    bool HandleSearchWheel(FVector2D Position,double Delta);
    void HandleStreamSearch(const FString& Json);
    UFUNCTION(BlueprintPure, Category="Warehouse Twin") FString GetSearchState(bool bGeometryOnly=false) const;
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual void NativeConstruct() override;
    virtual void NativeDestruct() override;
    virtual void NativeTick(const FGeometry& Geometry, float DeltaSeconds) override;
    virtual int32 NativePaint(const FPaintArgs&, const FGeometry&, const FSlateRect&, FSlateWindowElementList&, int32, const FWidgetStyle&, bool) const override;
private:
    void PushSnapshot(bool bExplicitSelection=false,bool bForce=false);
    void SetPanelCollapsed(bool bCollapsed,bool bExplicitSelection=false);
    void UpdateBrowserVisibility(bool bForce=false,bool bExplicitSelection=false);
    void RebuildPOICandidates(bool bAggregate);
    void UpdateVisiblePOIs(float DeltaSeconds,bool bRelayout);
    void UpdateSelectedScreenBounds();
    void Focus(const FString& Id);
    void Overview();
    void FocusRegion(const FString& Region);
    void RefreshSearch(int32 Offset=INDEX_NONE);
    void MoveSearchSelection(int32 Delta);
    void PushSearchState(bool bForce=false);
    bool SelectSearchResult(const FString& Id);
    FGHSTwinSearchLayout SearchLayout() const;
    UPROPERTY(Transient) TObjectPtr<UGHSTwinBrowser> Panel;
    UPROPERTY(Transient) TObjectPtr<UCanvasPanelSlot> PanelSlot;
    UPROPERTY(Transient) TObjectPtr<UGHSTwinSearchInput> SearchBox;
    UPROPERTY(Transient) TObjectPtr<UCanvasPanelSlot> SearchSlot;
    FGHSTwinSceneData SceneData;
    FGHSTwinLayout Layout;
    FVector2D ViewSize = FVector2D(1920,1080);
    double NextRefresh = 0;
    bool bPanelCollapsed = false, bShowPOIs = true, bEquipment = true, bRacks = true;
    bool bInitialViewPending = true;
    bool bBrowserActive=true,bDiagnostics=false;
    float PanelVisibilityProgress = 1.f;
    FGHSTwinPanelMotion PanelMotion;
    FString Density = TEXT("auto");
    FString PointFilter = TEXT("all");
    FString ActiveRegionId;
    FString SearchQuery,PendingSearchText,LastSearchState,SearchClientId;
    TArray<FGHSTwinSearchResult> SearchResults;
    int32 SearchTotal=0,SearchIndex=INDEX_NONE,SearchOffset=0,SearchFirstVisible=0;
    uint64 SearchRevision=MAX_uint64;
    double SearchRequestId=0;
    bool bSearchOpen=false,bSearchPending=false,bStreamSearchReady=false,bWarehouseMenuOpen=false;
    bool bSearchStateDirty=true,bStreamSearchApplying=false,bLastSearchVisible=false,bSearchIsRemote=false;
    float SearchMenuProgress=0,WarehouseMenuProgress=0;
    FVector2D LastSearchPosition=FVector2D::ZeroVector,LastSearchSize=FVector2D::ZeroVector,LastSearchViewport=FVector2D::ZeroVector;
    struct FLabel
    {
        FString Id,Text,Kind,Status,DisplayTitle,State;
        FVector WorldLocation=FVector::ZeroVector;
        FVector2D Position,Anchor,Size;
        FLinearColor Accent;
        bool bAlert=false,bSelected=false,bHovered=false,bRegion=false,bGroup=false;
        float Opacity=1;
        double BadgeWidth=0;
        FGHSTwinTextMetrics TitleMetrics,StateMetrics;
    };
    FGHSTwinPOIRefreshPolicy POICadence;
    TArray<FLabel> Labels;
    TArray<int32> VisibleLabels,PreviousVisibleLabels;
    TMap<FString,FVector2D> PreviousPositions;
    TMap<FString,float> LabelAges;
    FRotator LastLayoutRotation=FRotator::ZeroRotator;
    FVector LastLayoutLocation=FVector::ZeroVector;
    FVector2D SelectedScreenMin=FVector2D::ZeroVector,SelectedScreenMax=FVector2D::ZeroVector;
    bool bSelectedScreenBoundsValid=false;
    uint64 CandidateBuildCount=0,VisibleProjectionFrames=0,PointProjectionCount=0,SelectionProjectionCount=0;
};
