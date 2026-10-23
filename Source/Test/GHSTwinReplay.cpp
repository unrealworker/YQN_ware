#include "GHSTwinHUDWidget.h"
#include "GHSOrderReplaySession.h"
#include "GHSWarehousePlayerController.h"
#include "GHSWarehouseCameraPawn.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Components/CanvasPanelSlot.h"

namespace
{
FString WriteJson(const TSharedRef<FJsonObject>& Value)
{FString Json;FJsonSerializer::Serialize(Value,TJsonWriterFactory<>::Create(&Json));return Json;}
FString JString(const FString& Value)
{auto Object=MakeShared<FJsonObject>();Object->SetStringField(TEXT("v"),Value);return WriteJson(Object);}
}
UGHSOrderReplaySession* UGHSTwinHUDWidget::ReplaySession() const
{const auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer());return PC?PC->OrderReplay.Get():nullptr;}
bool UGHSTwinHUDWidget::IsReplayActive() const {const auto* Session=ReplaySession();return Session && Session->IsReplaying();}
FString UGHSTwinHUDWidget::GetReplayState() const
{const auto* Session=ReplaySession();return Session?Session->GetStateJson():TEXT("{\"active\":false}");}
void UGHSTwinHUDWidget::PushReplayState()
{
    const FString Script=TEXT("window.twinReplayReceive && window.twinReplayReceive(")+GetReplayState()+TEXT(");");
    if(Panel && bBrowserReady) Panel->Evaluate(Script);
    if(ReplayOverlay && bReplayOverlayReady) ReplayOverlay->Evaluate(Script);
}
bool UGHSTwinHUDWidget::GuardReplayOperation(const FString& Json,const FString& Title)
{
    auto* Session=ReplaySession();if(!Session || !Session->IsReplaying()) return false;
    TSharedPtr<FJsonObject> Object;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Object);
    if(!Object.IsValid()) return true;
    FString Action,Page;Object->TryGetStringField(TEXT("action"),Action);Object->TryGetStringField(TEXT("page"),Page);
    FString Target=Title;
    if(Target.IsEmpty())
    {
        if(Action==TEXT("navigate"))
        {
            static const TMap<FString,FString> Names{{TEXT("overview"),TEXT("总览")},{TEXT("inventory"),TEXT("库存")},{TEXT("orders"),TEXT("订单")},{TEXT("devices"),TEXT("设备")},{TEXT("alerts"),TEXT("告警")},{TEXT("trace"),TEXT("重新选择时间")},{TEXT("scene"),TEXT("场景设置")},{TEXT("settings"),TEXT("场景设置")}};
            Target=Names.FindRef(Page);
        }
        else if(Action==TEXT("overview")) Target=TEXT("全景视角");
        else if(Action==TEXT("select") || Action==TEXT("focus")) Target=TEXT("设备定位");
        else if(Action==TEXT("preset")) Target=TEXT("预设视角");
        else Target=TEXT("原场景操作");
    }
    Session->RequestExit(Json,TEXT("停止追溯并前往")+Target+TEXT("？"),TEXT("停止并前往")+Target);
    SetPanelCollapsed(false);PushReplayState();return true;
}
void UGHSTwinHUDWidget::ReplayOverview()
{
    auto* Session=ReplaySession();if(!Session || !Session->IsReplaying() || Session->IsExitPending()) return;
    Session->Follow(TEXT(""),ViewSize,Layout.ScenePosition+Layout.SceneSize*.5);
    if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(GetOwningPlayerPawn()))
        Camera->FocusOnTarget(Camera->OverviewCenter,FMath::Min(Camera->MaximumZoom,
            float(Camera->OverviewDistance*ViewSize.X/FMath::Max(1.,Layout.SceneSize.X))),FRotator(-54,-90,0),ViewSize,
            Layout.ScenePosition+FVector2D(Layout.SceneSize.X*.5,(Layout.SceneSize.Y-168)*.5));
}
bool UGHSTwinHUDWidget::HandleReplayCommand(const FString& Action,const TSharedPtr<FJsonObject>& Object)
{
    auto* Session=ReplaySession();if(!Session) return false;
    FString Id;Object->TryGetStringField(TEXT("id"),Id);
    const FVector2D Center=Layout.ScenePosition+FVector2D(Layout.SceneSize.X*.5,(Layout.SceneSize.Y-168)*.5);
    if(Action==TEXT("replayReady")) {bReplayOverlayReady=true;LastReplayViewport=FVector2D::ZeroVector;PushReplayState();return true;}
    if(Action==TEXT("replayStart"))
    {
        if(Session->IsReplaying()) {GuardReplayOperation(TEXT("{\"action\":\"navigate\",\"page\":\"trace\"}"),TEXT("重新选择订单"));return true;}
        FString Order,Start,End;Object->TryGetStringField(TEXT("orderId"),Order);Object->TryGetStringField(TEXT("startUtc"),Start);Object->TryGetStringField(TEXT("endUtc"),End);
        if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwningPlayer())) PC->CancelCameraDrag();
        SceneData.CaptureVisibilityOverrides();
        if(Session->Start(Order,Start,End))
        {
            PreReplaySelectedId=SelectedId;PreReplayRegionId=ActiveRegionId;
            SelectedId.Empty();ActiveRegionId.Empty();PendingInteriorAction.Empty();PendingInteriorId.Empty();
            bSelectedScreenBoundsValid=false;bWarehousePOIVisible=false;
            VisibleLabels.Reset();PreviousVisibleLabels.Reset();Labels.Reset();
            SetSearchOpen(false);bWarehouseMenuOpen=false;SetPanelCollapsed(false);
            ReplayOverview();
        }
    }
    else if(Action==TEXT("replayPlay")) Session->Play();
    else if(Action==TEXT("replayPause")) Session->Pause();
    else if(Action==TEXT("replaySeek")) {double Time;if(Object->TryGetNumberField(TEXT("time"),Time)) Session->Seek(Time);}
    else if(Action==TEXT("replayRate")) {double Rate;if(Object->TryGetNumberField(TEXT("rate"),Rate)) Session->SetRate(Rate);}
    else if(Action==TEXT("replaySelect")) Session->Select(Id);
    else if(Action==TEXT("replayFollow")) Session->Follow(Id,ViewSize,Center);
    else if(Action==TEXT("replayTrails")) {FString Mode;if(Object->TryGetStringField(TEXT("mode"),Mode)) Session->SetTrails(Mode);}
    else if(Action==TEXT("replayEvents"))
    {double Start=0,End=0;bool Reset=false;Object->TryGetNumberField(TEXT("start"),Start);Object->TryGetNumberField(TEXT("end"),End);Object->TryGetBoolField(TEXT("reset"),Reset);Session->SetEventWindow(Start,End,Reset);}
    else if(Action==TEXT("replayOverview")) ReplayOverview();
    else if(Action==TEXT("replayEndRequest"))
    {Session->RequestExit(TEXT("{\"action\":\"replayEnd\"}"),TEXT("结束追溯？"),TEXT("结束并恢复场景"));SetPanelCollapsed(false);}
    else if(Action==TEXT("replayLeave"))
    {
        FString Title;Object->TryGetStringField(TEXT("title"),Title);
        GuardReplayOperation(WriteJson(Object.ToSharedRef()),Title.IsEmpty()?TEXT("其他操作"):Title);
    }
    else if(Action==TEXT("replayExitCancel")) Session->CancelExit();
    else if(Action==TEXT("replayExitConfirm"))
    {
        if(!Session->IsExitPending()) return true;
        const FString Pending=Session->ConfirmExit();
        if(!Session->IsReplaying())
        {
            SelectedId=PreReplaySelectedId;ActiveRegionId=PreReplayRegionId;POICadence.Invalidate();
            // Resume catalogue refresh only after source instance/visibility restoration.
            NextRefresh=0;PushSceneControls(TEXT(""),true);PushReplayState();
        }
        TSharedPtr<FJsonObject> Intent;
        if(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Pending),Intent) && Intent.IsValid())
        {
            FString PendingAction;Intent->TryGetStringField(TEXT("action"),PendingAction);
            if(PendingAction==TEXT("replayLeave"))
            {
                FString Token;Intent->TryGetStringField(TEXT("token"),Token);
                if(Panel) Panel->Evaluate(TEXT("window.twinReplayContinue && window.twinReplayContinue((")+JString(Token)+TEXT(").v);"));
            }
            else if(PendingAction==TEXT("navigate")) {FString Page;Intent->TryGetStringField(TEXT("page"),Page);Navigate(Page);}
            else if(PendingAction==TEXT("replayEnd")) {if(Panel) Panel->Evaluate(TEXT("window.twinNavigate && window.twinNavigate('trace');"));}
            else Command(Pending);
        }
    }
    PushReplayState();return true;
}
