#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Layout/SlateRect.h"

class SConstraintCanvas;

/** A single projection snapshot, in physical viewport pixels. */
struct FGHSGlobeScreenMarker
{
    FString Id, Name;
    TArray<FString> Ids;
    FVector2D PointPixels = FVector2D::ZeroVector;
    bool bSelected = false;
    bool IsCluster() const { return Ids.Num() > 1; }
};

/** Shared by painting and hit-test layout; camera distance is deliberately absent. */
struct TEST_API FGHSGlobePOIGeometry
{
    static constexpr float PointDiameter = 20.f;
    static constexpr float HaloDiameter = 36.f;
    FVector2D CardPosition, CardSize, LineStart, LineEnd;
    static FGHSGlobePOIGeometry Make(FVector2D PointPixels, const FSlateRect& SceneRect, bool bCluster = false);
    static FGHSGlobePOIGeometry AvoidOverlaps(FVector2D PointPixels, const FSlateRect& SceneRect,
        const TArray<FSlateRect>& Occupied, bool bCluster = false);
};

DECLARE_DELEGATE_OneParam(FGHSGlobeMarkerAction, const FString&);
DECLARE_DELEGATE_OneParam(FGHSGlobeClusterAction, const TArray<FString>&);
DECLARE_DELEGATE_OneParam(FGHSGlobeOverlayInteraction, bool);

/** Native labels, leaders and fixed-pixel points share one current-camera snapshot. */
class TEST_API SGHSGlobeWarehouseOverlay : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SGHSGlobeWarehouseOverlay) {}
        SLATE_EVENT(FGHSGlobeMarkerAction, OnSelect)
        SLATE_EVENT(FGHSGlobeMarkerAction, OnEnter)
        SLATE_EVENT(FGHSGlobeClusterAction, OnCluster)
        SLATE_EVENT(FGHSGlobeOverlayInteraction, OnInteraction)
    SLATE_END_ARGS()

    void Construct(const FArguments& Args);
    void SetMarkers(const TArray<FGHSGlobeScreenMarker>& InMarkers);
    void SetSceneRect(const FSlateRect& InSceneRect);
    virtual void Tick(const FGeometry& Geometry, double Time, float DeltaTime) override;
    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& CullingRect,
        FSlateWindowElementList& Elements, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const override;

private:
    struct FEntry;
    TSharedPtr<SConstraintCanvas> Canvas;
    TMap<FString, TSharedPtr<FEntry>> Entries;
    TArray<FString> OrderedIds;
    FSlateRect SceneRect = FSlateRect(0, 0, 1920, 1080);
    float PixelUnit = 1.f;
    bool bWasInteracting = false;
    FGHSGlobeMarkerAction OnSelect, OnEnter;
    FGHSGlobeClusterAction OnCluster;
    FGHSGlobeOverlayInteraction OnInteraction;
};
