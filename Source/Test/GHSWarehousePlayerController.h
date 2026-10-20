#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "GHSWarehousePlayerController.generated.h"

class UGHSDockTruckHUDWidget;
class UGHSTwinHUDWidget;

UENUM(BlueprintType)
enum class EGHSWarehouseDragMode : uint8 { None, Orbit, Pan };

UCLASS(Blueprintable)
class TEST_API AGHSWarehousePlayerController : public APlayerController
{
    GENERATED_BODY()
public:
    AGHSWarehousePlayerController();
    virtual bool InputKey(const FInputKeyParams& Params) override;
    virtual void PlayerTick(float DeltaSeconds) override;
    virtual void FlushPressedKeys() override;
    virtual bool ShouldFlushKeysWhenViewportFocusChanges() const override { return true; }
    UPROPERTY(BlueprintReadOnly, Category="Warehouse Camera")
    EGHSWarehouseDragMode DragMode = EGHSWarehouseDragMode::None;
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Warehouse Camera", meta=(ClampMin="0", ClampMax="12"))
    float DragThresholdPixels = 3.0f;
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    void CancelCameraDrag();
    /** Grab the ground under the visible cursor using the camera plugin. */
    UFUNCTION(BlueprintCallable, Category="Warehouse Camera")
    bool BeginMapDrag();
    /** Validate the live cursor/ray before the plugin updates its ground anchor. */
    bool HasValidMapDragCursor() const;
    UPROPERTY(BlueprintReadOnly, Transient, Category="Dock Truck HUD")
    TObjectPtr<UGHSDockTruckHUDWidget> TruckHUDWidget;
    UPROPERTY(BlueprintReadOnly, Transient, Category="Warehouse Twin")
    TObjectPtr<UGHSTwinHUDWidget> TwinHUDWidget;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void OnUnPossess() override;
private:
    void ConsumeOrbitMotion();
    void FinishTwinOrbitRelease();
    FVector2D PendingMouse = FVector2D::ZeroVector;
    FVector2D DragTravel = FVector2D::ZeroVector;
    bool bPastDragThreshold = false;
    bool bTwinOrbitReleasePending = false;
    bool bManualDoubleClickCapture = false;
    FIntPoint DoubleClickCursorPosition = FIntPoint::ZeroValue;
    FIntPoint MapDragViewportSize = FIntPoint::ZeroValue;
    FVector2D TwinPressPosition = FVector2D::ZeroVector;
    TSharedPtr<SWidget> TwinViewportWidget;
};
