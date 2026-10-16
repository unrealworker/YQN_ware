#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/PlayerInput.h"
#include "UnrealClient.h"

AGHSWarehousePlayerController::AGHSWarehousePlayerController()
{
    bShowMouseCursor = true;
    bEnableClickEvents = false;
    bEnableMouseOverEvents = false;
}

void AGHSWarehousePlayerController::BeginPlay()
{
    Super::BeginPlay();
    FInputModeGameAndUI Mode;
    Mode.SetHideCursorDuringCapture(true);
    Mode.SetLockMouseToViewportBehavior(EMouseLockMode::LockOnCapture);
    SetInputMode(Mode);
    if (ULocalPlayer* Local = GetLocalPlayer())
    {
        if (UGameViewportClient* Viewport = Local->ViewportClient)
        {
            Viewport->SetMouseCaptureMode(EMouseCaptureMode::CaptureDuringMouseDown);
            Viewport->SetHideCursorDuringCapture(true);
        }
    }
}

bool AGHSWarehousePlayerController::InputKey(const FInputKeyParams& Params)
{
    const bool bHandled = Super::InputKey(Params);
    AGHSWarehouseCameraPawn* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn());
    if (!Camera || Params.IsGamepad()) return bHandled;
    const FKey Key = Params.Key;
    if (Key == EKeys::LeftMouseButton || Key == EKeys::RightMouseButton)
    {
        const auto Requested = Key == EKeys::LeftMouseButton ? EGHSWarehouseDragMode::Orbit : EGHSWarehouseDragMode::Pan;
        if ((Params.Event == IE_Pressed || Params.Event == IE_DoubleClick) && DragMode == EGHSWarehouseDragMode::None)
        {
            CancelCameraDrag();
            DragMode = Requested;
            // SceneViewport's double-click route does not acquire capture as
            // its ordinary button-down route does. Support click-then-drag too.
            if (Params.Event == IE_DoubleClick)
            {
                if (ULocalPlayer* Local = GetLocalPlayer())
                {
                    FViewport* Viewport = Local->ViewportClient ? Local->ViewportClient->Viewport : nullptr;
                    if (Viewport)
                    {
                        DoubleClickCursorPosition = FIntPoint(Viewport->GetMouseX(), Viewport->GetMouseY());
                        bManualDoubleClickCapture = true;
                        bShowMouseCursor = false;
                        Viewport->CaptureMouse(true);
                        Viewport->LockMouseToViewport(true);
                    }
                }
            }
        }
        else if (Params.Event == IE_Released && DragMode == Requested) CancelCameraDrag();
        return true;
    }
    if (Key == EKeys::Home && Params.Event == IE_Pressed)
    {
        CancelCameraDrag(); Camera->ResetOverview(); return true;
    }
    if (Key == EKeys::MouseWheelAxis)
    {
        Camera->ZoomSteps(float(Params.Delta.X)); return true;
    }
    if (Key == EKeys::MouseX || Key == EKeys::MouseY)
    {
        // Read viewport deltas before legacy axis sensitivity, FOV scaling and
        // mouse smoothing. The plugin supplies one predictable smoothing stage.
        if (DragMode != EGHSWarehouseDragMode::None && FMath::IsFinite(Params.Delta.X))
        {
            if (Key == EKeys::MouseX) PendingMouse.X += Params.Delta.X;
            else PendingMouse.Y -= Params.Delta.X;
        }
        return true;
    }
    return bHandled;
}

void AGHSWarehousePlayerController::PlayerTick(float DeltaSeconds)
{
    Super::PlayerTick(DeltaSeconds);
    if (ULocalPlayer* Local = GetLocalPlayer())
    {
        FViewport* Viewport = Local->ViewportClient ? Local->ViewportClient->Viewport : nullptr;
        if (!Viewport || !Viewport->HasFocus() || !Viewport->IsForegroundWindow()) CancelCameraDrag();
    }
    auto* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn());
    if (!Camera || DragMode == EGHSWarehouseDragMode::None) { PendingMouse = FVector2D::ZeroVector; return; }
    FVector2D Delta = PendingMouse;
    PendingMouse = FVector2D::ZeroVector;
    if (!bPastDragThreshold)
    {
        DragTravel += Delta;
        if (DragTravel.Size() < DragThresholdPixels) return;
        bPastDragThreshold = true;
        Delta = DragTravel;
    }
    if (DragMode == EGHSWarehouseDragMode::Orbit) Camera->OrbitPixels(Delta);
    else
    {
        int32 Width = 0, Height = 0;
        GetViewportSize(Width, Height);
        Camera->PanPixels(Delta, Width);
    }
}

void AGHSWarehousePlayerController::CancelCameraDrag()
{
    if (bManualDoubleClickCapture)
    {
        bManualDoubleClickCapture = false;
        bShowMouseCursor = true;
        if (ULocalPlayer* Local = GetLocalPlayer())
        {
            FViewport* Viewport = Local->ViewportClient ? Local->ViewportClient->Viewport : nullptr;
            if (Viewport)
            {
                Viewport->CaptureMouse(false);
                Viewport->LockMouseToViewport(false);
                if (Viewport->HasFocus() && Viewport->IsForegroundWindow())
                    SetMouseLocation(DoubleClickCursorPosition.X, DoubleClickCursorPosition.Y);
            }
        }
    }
    DragMode = EGHSWarehouseDragMode::None;
    PendingMouse = DragTravel = FVector2D::ZeroVector;
    bPastDragThreshold = false;
}

void AGHSWarehousePlayerController::FlushPressedKeys()
{
    CancelCameraDrag();
    Super::FlushPressedKeys();
}

void AGHSWarehousePlayerController::OnUnPossess()
{
    CancelCameraDrag();
    Super::OnUnPossess();
}
