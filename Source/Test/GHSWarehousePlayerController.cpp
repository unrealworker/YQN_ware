#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSDockTruckHUDWidget.h"
#include "GHSTwinHUDWidget.h"
#include "GHSTwinViewport.h"
#include "GHSWarehouseRoofComponent.h"
#include "GHSCampusTrafficActor.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/PlayerInput.h"
#include "UnrealClient.h"
#include "SceneView.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "Widgets/Layout/SDPIScaler.h"
#include "Slate/SceneViewport.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "PixelStreamingInputComponent.h"

namespace
{
bool TraceTwinInput()
{
    static const bool bEnabled = FParse::Param(FCommandLine::Get(), TEXT("TwinInputTrace"));
    return bEnabled;
}
}

AGHSWarehousePlayerController::AGHSWarehousePlayerController()
{
    bShowMouseCursor = true;
    bEnableClickEvents = false;
    bEnableMouseOverEvents = false;
    SearchStreamingInput=CreateDefaultSubobject<UPixelStreamingInput>(TEXT("SceneSearchStreamingInput"));
    WarehouseRoof=CreateDefaultSubobject<UGHSWarehouseRoofComponent>(TEXT("WarehouseRoof"));
}

void AGHSWarehousePlayerController::BeginPlay()
{
    Super::BeginPlay();
    if(SearchStreamingInput) SearchStreamingInput->OnInputEvent.AddDynamic(this,&AGHSWarehousePlayerController::HandleStreamingInput);
    if (IsLocalController() && GetWorld()->GetMapName().Contains(TEXT("GHS_CAD_NormalWarehouse")))
    {
        if (GetWorld()->GetMapName().Contains(TEXT("ZcoolSmartFactory")))
        {
            CampusTraffic=GetWorld()->SpawnActor<AGHSCampusTrafficActor>();
            TwinHUDWidget = CreateWidget<UGHSTwinHUDWidget>(this);
            if (TwinHUDWidget && GetWorld()->GetGameViewport())
            {
                // The warehouse has its own 1080p design scale. The surrounding
                // game layer already normalizes Windows DPI; cancel only its curve.
                TwinViewportWidget = SNew(SDPIScaler)
                    .DPIScale_Lambda([this]()
                    {
                        FVector2D Pixels(1920,1080);
                        if(GetWorld() && GetWorld()->GetGameViewport()) GetWorld()->GetGameViewport()->GetViewportSize(Pixels);
                        return float(FGHSTwinViewport::FromPixels(Pixels).SlateScale(UWidgetLayoutLibrary::GetViewportScale(this)));
                    })
                    [TwinHUDWidget->TakeWidget()];
                GetWorld()->GetGameViewport()->AddViewportWidgetContent(TwinViewportWidget.ToSharedRef(),20);
            }
        }
        else
        {
            TruckHUDWidget = CreateWidget<UGHSDockTruckHUDWidget>(this);
            if (TruckHUDWidget) TruckHUDWidget->AddToViewport(20);
        }
    }
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

void AGHSWarehousePlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if(SearchStreamingInput) SearchStreamingInput->OnInputEvent.RemoveDynamic(this,&AGHSWarehousePlayerController::HandleStreamingInput);
    CancelCameraDrag();
    if (TruckHUDWidget) { TruckHUDWidget->RemoveFromParent(); TruckHUDWidget = nullptr; }
    if (TwinViewportWidget.IsValid() && GetWorld()->GetGameViewport()) GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(TwinViewportWidget.ToSharedRef());
    TwinViewportWidget.Reset(); TwinHUDWidget=nullptr;
    if(CampusTraffic) { CampusTraffic->Destroy(); CampusTraffic=nullptr; }
    Super::EndPlay(EndPlayReason);
}

bool AGHSWarehousePlayerController::InputKey(const FInputKeyParams& Params)
{
    // A second press may precede Slate's final axis batch too. Discard the old
    // click candidate rather than interpreting zero received pixels as a tap.
    if (bTwinOrbitReleasePending && (Params.Event == IE_Pressed || Params.Event == IE_DoubleClick)
        && (Params.Key == EKeys::LeftMouseButton || Params.Key == EKeys::RightMouseButton))
        CancelCameraDrag();
    const bool bHandled = Super::InputKey(Params);
    AGHSWarehouseCameraPawn* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn());
    if (!Camera || Params.IsGamepad()) return bHandled;
    const FKey Key = Params.Key;
    if (TwinHUDWidget && TraceTwinInput() && (Key == EKeys::LeftMouseButton || Key == EKeys::MouseX || Key == EKeys::MouseY))
        UE_LOG(LogTemp, Display, TEXT("GHS_TWIN_INPUT frame=%llu key=%s event=%d delta=%.2f mode=%d pending=%s releasing=%d"),
            GFrameCounter, *Key.ToString(), int32(Params.Event), Params.Delta.X, int32(DragMode), *PendingMouse.ToString(), bTwinOrbitReleasePending);
    if (TwinHUDWidget)
    {
        if(Params.Event==IE_Pressed && TwinHUDWidget->HandleSearchKey(Key)) {CancelCameraDrag();return true;}
        if(Key==EKeys::Escape && Params.Event==IE_Pressed) { TwinHUDWidget->ClearSelection(); CancelCameraDrag(); return true; }
        if(Key==EKeys::LeftMouseButton || Key==EKeys::RightMouseButton || Key==EKeys::MiddleMouseButton || Key==EKeys::MouseWheelAxis)
        {
            FVector2D Cursor;
            if(GetMousePosition(Cursor.X,Cursor.Y))
            {
                if(Key==EKeys::MouseWheelAxis && TwinHUDWidget->HandleSearchWheel(Cursor,Params.Delta.X)) {CancelCameraDrag();return true;}
                if(Key==EKeys::LeftMouseButton && Params.Event==IE_Pressed && TwinHUDWidget->HandleChromeClick(Cursor)) { CancelCameraDrag(); return true; }
                if(!TwinHUDWidget->IsScenePoint(Cursor)) { CancelCameraDrag(); return true; }
                if(Key==EKeys::LeftMouseButton && (Params.Event==IE_Pressed || Params.Event==IE_DoubleClick)) TwinPressPosition=Cursor;
            }
        }
    }
    if (Key == EKeys::Escape && Params.Event == IE_Pressed && TruckHUDWidget &&
        (TruckHUDWidget->bDetailVisible || TruckHUDWidget->bClusterListVisible || !TruckHUDWidget->GetSelectedEquipmentId().IsEmpty()))
    {
        TruckHUDWidget->ClearSelection(); CancelCameraDrag(); return true;
    }
    if (Key == EKeys::LeftMouseButton || Key == EKeys::RightMouseButton)
    {
        const auto Requested = Key == EKeys::LeftMouseButton ? EGHSWarehouseDragMode::Orbit : EGHSWarehouseDragMode::Pan;
        if ((Params.Event == IE_Pressed || Params.Event == IE_DoubleClick) && DragMode == EGHSWarehouseDragMode::None)
        {
            CancelCameraDrag();
            DragMode = Requested;
            if (Requested == EGHSWarehouseDragMode::Pan)
            {
                BeginMapDrag();
            }
            else if (ULocalPlayer* Local = GetLocalPlayer())
            {
                if (Local->ViewportClient) Local->ViewportClient->SetHideCursorDuringCapture(true);
            }
            // SceneViewport's double-click route does not acquire capture as
            // its ordinary button-down route does. Support click-then-drag too.
            if (Params.Event == IE_DoubleClick && Requested == EGHSWarehouseDragMode::Orbit)
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
        else if (Params.Event == IE_Released && DragMode == Requested)
        {
            // Slate sends button-up before its accumulated MouseX/Y for this
            // frame. Decide click vs drag only after that batch reaches us.
            if (TwinHUDWidget && Requested == EGHSWarehouseDragMode::Orbit)
            {
                // Flush while the scene still owns pointer capture. After
                // button-up Slate can route FinishedPointerInput to a different
                // widget, losing this gesture's final batch before our Tick.
                if (ULocalPlayer* Local = GetLocalPlayer())
                    if (Local->ViewportClient)
                        if (FSceneViewport* SceneViewport = Local->ViewportClient->GetGameViewport())
                            SceneViewport->OnFinishedPointerInput();
                bTwinOrbitReleasePending = true;
            }
            else
                CancelCameraDrag();
        }
        return true;
    }
    if ((Key == EKeys::Home && Params.Event == IE_Pressed)
        || (Key == EKeys::MiddleMouseButton && (Params.Event == IE_Pressed || Params.Event == IE_DoubleClick)))
    {
        CancelCameraDrag(); if(TwinHUDWidget) TwinHUDWidget->Command(TEXT("{\"action\":\"overview\"}")); else Camera->ResetOverview(); return true;
    }
    if (Key == EKeys::MouseWheelAxis)
    {
        if (DragMode == EGHSWarehouseDragMode::Pan) CancelCameraDrag();
        Camera->ZoomSteps(float(Params.Delta.X)); return true;
    }
    if (Key == EKeys::MouseX || Key == EKeys::MouseY)
    {
        // Read viewport deltas before legacy axis sensitivity, FOV scaling and
        // mouse smoothing. The plugin supplies one predictable smoothing stage.
        if (DragMode == EGHSWarehouseDragMode::Orbit && FMath::IsFinite(Params.Delta.X))
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
    if (DragMode == EGHSWarehouseDragMode::Pan)
    {
        PendingMouse = FVector2D::ZeroVector;
        // The plugin updates the grabbed point once in the Pawn's Tick.
        if (!Camera->IsPreciseMouseDragging || !HasValidMapDragCursor()) CancelCameraDrag();
        return;
    }
    ConsumeOrbitMotion();
    if (bTwinOrbitReleasePending) FinishTwinOrbitRelease();
}

void AGHSWarehousePlayerController::ConsumeOrbitMotion()
{
    auto* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn());
    if (!Camera || DragMode != EGHSWarehouseDragMode::Orbit) return;
    FVector2D Delta = PendingMouse;
    PendingMouse = FVector2D::ZeroVector;
    if (!bPastDragThreshold)
    {
        DragTravel += Delta;
        if (DragTravel.Size() < DragThresholdPixels) return;
        bPastDragThreshold = true;
        Delta = DragTravel;
    }
    Camera->OrbitPixels(Delta);
}

void AGHSWarehousePlayerController::FinishTwinOrbitRelease()
{
    if (TraceTwinInput()) UE_LOG(LogTemp, Display, TEXT("GHS_TWIN_RELEASE frame=%llu pending=%s travel=%s past=%d"),
        GFrameCounter, *PendingMouse.ToString(), *DragTravel.ToString(), bPastDragThreshold);
    ConsumeOrbitMotion();
    const bool bSceneClick = !bPastDragThreshold;
    const FVector2D PressPosition = TwinPressPosition;
    CancelCameraDrag();
    if (bSceneClick && TwinHUDWidget) TwinHUDWidget->HandleSceneClick(PressPosition);
}

bool AGHSWarehousePlayerController::BeginMapDrag()
{
    if (DragMode == EGHSWarehouseDragMode::Orbit) return false;
    CancelCameraDrag();
    auto* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn());
    if (!Camera || !HasValidMapDragCursor()) return false;
    Camera->PrepareForGroundPan();
    ULocalPlayer* Local = GetLocalPlayer();
    MapDragViewportSize = Local->ViewportClient->Viewport->GetSizeXY();

    // Stop unfinished easing at the actual view, without jumping to its target.
    Camera->FreezeCurrentPose();
    Camera->EnableFeatures(EEnabledFeatures::PreciseMouseDrag);
    Camera->PreciseMouseDragMode = EPreciseMouseDragMode::Plane;
    Camera->PreciseMouseDragPoint = FVector::ZeroVector;
    Camera->PreciseMouseDragNormal = FVector::UpVector;
    Camera->PreciseMouseDragIgnoreMovementLag = true;
    Camera->TogglePreciseMouseDrag(true);
    if (!Camera->IsPreciseMouseDragging) return false;
    DragMode = EGHSWarehouseDragMode::Pan;
    bShowMouseCursor = true;
    // Called during InputKey, before SceneViewport acquires ordinary capture.
    // Visible absolute cursor tracking must not use high-precision recentering.
    Local->ViewportClient->SetHideCursorDuringCapture(false);
    return true;
}

bool AGHSWarehousePlayerController::HasValidMapDragCursor() const
{
    ULocalPlayer* Local = GetLocalPlayer();
    FViewport* Viewport = Local && Local->ViewportClient ? Local->ViewportClient->Viewport : nullptr;
    FSceneViewProjectionData Projection;
    if (!Viewport || !Local->GetProjectionData(Viewport, Projection) || !Projection.IsValidViewRectangle()) return false;
    if (DragMode == EGHSWarehouseDragMode::Pan && MapDragViewportSize != Viewport->GetSizeXY()) return false;
    FVector2D Position;
    const FIntRect Rect = Projection.GetConstrainedViewRect();
    if (!GetMousePosition(Position.X, Position.Y)
        || !FMath::IsFinite(Position.X) || !FMath::IsFinite(Position.Y)
        || Position.X < Rect.Min.X || Position.Y < Rect.Min.Y
        || Position.X >= Rect.Max.X || Position.Y >= Rect.Max.Y) return false;
    if(TwinHUDWidget && !TwinHUDWidget->IsScenePoint(Position)) return false;
    FVector Origin, Direction;
    return DeprojectScreenPositionToWorld(Position.X, Position.Y, Origin, Direction)
        && !Origin.ContainsNaN() && !Direction.ContainsNaN()
        && Origin.Z > 0 && Direction.Z < -1.e-6;
}

void AGHSWarehousePlayerController::CancelCameraDrag()
{
    if (auto* Camera = Cast<AGHSWarehouseCameraPawn>(GetPawn()))
    {
        if (Camera->IsPreciseMouseDragging)
        {
            Camera->TogglePreciseMouseDrag(false);
            Camera->FreezeCurrentPose();
        }
    }
    MapDragViewportSize = FIntPoint::ZeroValue;
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
    bTwinOrbitReleasePending = false;
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

void AGHSWarehousePlayerController::HandleStreamingInput(const FString& Descriptor)
{ if(IsLocalController() && TwinHUDWidget) TwinHUDWidget->HandleStreamSearch(Descriptor); }
void AGHSWarehousePlayerController::SendSearchResponse(const FString& Json)
{ if(SearchStreamingInput) SearchStreamingInput->SendPixelStreamingResponse(Json); }
