#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "GHSWarehousePlayerController.generated.h"

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
protected:
    virtual void BeginPlay() override;
    virtual void OnUnPossess() override;
private:
    FVector2D PendingMouse = FVector2D::ZeroVector;
    FVector2D DragTravel = FVector2D::ZeroVector;
    bool bPastDragThreshold = false;
    bool bManualDoubleClickCapture = false;
    FIntPoint DoubleClickCursorPosition = FIntPoint::ZeroValue;
};
