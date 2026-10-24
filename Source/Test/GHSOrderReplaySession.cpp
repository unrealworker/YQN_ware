#include "GHSOrderReplaySession.h"
#include "GHSOrderReplayActor.h"
#include "GHSWarehousePlayerController.h"
#include "GHSCampusTrafficActor.h"
#include "GHSTwinSceneData.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

namespace
{
FString WriteSessionJson(const TSharedRef<FJsonObject>& Object)
{FString Out;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Out));return Out;}
TArray<TSharedPtr<FJsonValue>> ArrayJson(const FString& Text)
{TArray<TSharedPtr<FJsonValue>> Values;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Values);return Values;}
bool EquipmentActor(AActor* Actor)
{
    GHSTwinSelection::FIdentity Identity;
    if(GHSTwinSelection::Identify(Actor->Tags,Identity)) return true;
    if(Actor->IsA<AGHSCampusTrafficActor>()) return true;
    for(const FName Tag:Actor->Tags)
        if(Tag.ToString().StartsWith(TEXT("FXOwner=")) || Tag==TEXT("AGVAnimatedFX")) return true;
    for(auto* Component:Actor->GetComponents()) if(auto* Mesh=Cast<UStaticMeshComponent>(Component))
        if(Mesh->GetStaticMesh() && Mesh->GetStaticMesh()->GetPathName().Contains(TEXT("SM_GHSPark_ClosedTruck"))) return true;
    return false;
}
}

bool FGHSReplayClock::Start(double Seconds)
{
    if(!FMath::IsFinite(Seconds) || Seconds<3600) return false;
    Time=0;Duration=Seconds;Rate=1;Playing=true;return true;
}
void FGHSReplayClock::Advance(double Seconds)
{
    if(!Playing || !FMath::IsFinite(Seconds) || Seconds<=0) return;
    Time=FMath::Min(Duration,Time+Seconds*Rate);if(Completed()) Playing=false;
}
void FGHSReplayClock::Seek(double Seconds)
{if(FMath::IsFinite(Seconds)) {Time=FMath::Clamp(Seconds,0.,Duration);if(Completed()) Playing=false;}}
void FGHSReplayClock::SetRate(double Value)
{for(double R:{1.,2.,4.,8.,16.,32.,64.}) if(Value==R) {Rate=R;return;}}
bool FGHSReplayExitGuard::Request(const FString& Value,FGHSReplayClock& Clock)
{if(Pending() || Value.IsEmpty()) return false;Intent=Value;WasPlaying=Clock.Playing;Clock.Playing=false;return true;}
void FGHSReplayExitGuard::Cancel(FGHSReplayClock& Clock)
{if(!Pending()) return;Clock.Playing=WasPlaying && !Clock.Completed();Intent.Empty();}
FString FGHSReplayExitGuard::Consume() {FString Result=MoveTemp(Intent);Intent.Empty();return Result;}

UGHSOrderReplaySession::UGHSOrderReplaySession() {PrimaryComponentTick.bCanEverTick=false;}
void UGHSOrderReplaySession::EndPlay(const EEndPlayReason::Type Reason) {Stop();Super::EndPlay(Reason);}
bool UGHSOrderReplaySession::Start(const FString& Order,const FString& Start,const FString& End)
{
    if(bActive) return false;
    Error.Empty();FDateTime From,To;
    const bool bOrder=Order==TEXT("TEST-OUT-001") || Order==TEXT("TEST-OUT-002") || Order==TEXT("TEST-OUT-003") || Order==TEXT("TEST-OUT-004");
    if(!bOrder || !Start.EndsWith(TEXT("Z")) || !End.EndsWith(TEXT("Z")) || !FDateTime::ParseIso8601(*Start,From) || !FDateTime::ParseIso8601(*End,To) || !Clock.Start((To-From).GetTotalSeconds()))
    {Error=TEXT("请选择有效的测试订单与至少一小时的时间段。");return false;}
    OrderId=Order;StartUtc=Start;EndUtc=End;SelectedId.Empty();FollowId.Empty();TrailMode=TEXT("all");Exit=FGHSReplayExitGuard();
    CachedMarkers.Reset();EventWindowStart=EventWindowEnd=-1;
    FActorSpawnParameters Spawn;Spawn.ObjectFlags|=RF_Transient;Spawn.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    Replay=GetWorld()->SpawnActor<AGHSOrderReplayActor>(FVector::ZeroVector,FRotator::ZeroRotator,Spawn);
    if(!Replay || !Replay->InitializeReplay())
    {Error=Replay?Replay->GetError():TEXT("无法创建回放场景");if(Replay) Replay->Destroy();Replay=nullptr;return false;}
    Replay->SetPlaybackEndTime(Clock.Duration);
    // Prepare all assets first; a failure must not leave a partially cleared scene.
    if(!LoadParkingAlternates()) {Replay->Destroy();Replay=nullptr;return false;}
    CaptureAndIsolate();
    if(!HideSourceInstances()) {Restore();Replay->Destroy();Replay=nullptr;return false;}
    bActive=true;bPreparing=true;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner());PC && PC->WarehouseRoof) PC->WarehouseRoof->OpenRoof(true);
    Replay->EvaluateAt(0);Replay->SetTrailMode(TrailMode,SelectedId);
    return true;
}
bool UGHSOrderReplaySession::LoadParkingAlternates()
{
    FString Text;
    if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/order-replay-parking.json"))))
    {Error=TEXT("回放停车车辆分离资源尚未准备完成。");return false;}
    const auto Entries=ArrayJson(Text);ParkingAlternates.Reset();Meshes.Reset();
    for(const auto& Value:Entries)
    {
        const auto Object=Value->AsObject();if(!Object.IsValid()) continue;
        FString Source,Replacement;Object->TryGetStringField(TEXT("source"),Source);Object->TryGetStringField(TEXT("replacement"),Replacement);
        bool Hide=false;Object->TryGetBoolField(TEXT("hide"),Hide);
        UStaticMesh* Alternate=Hide?nullptr:LoadObject<UStaticMesh>(nullptr,*Replacement);
        if(!Hide && !Alternate) {Error=TEXT("回放停车车辆资源加载失败: ")+Replacement;return false;}
        ParkingAlternates.Add(Alternate);
        // Only matching geometry is replaced. Existing materials, transforms and visibility stay untouched.
        for(TActorIterator<AActor> It(GetWorld());It;++It) for(auto* Component:It->GetComponents())
            if(auto* Mesh=Cast<UStaticMeshComponent>(Component);Mesh && Mesh->GetStaticMesh() &&
                (Mesh->GetStaticMesh()->GetPathName()==Source || Mesh->GetStaticMesh()->GetPathName().StartsWith(Source+TEXT("."))))
                Meshes.Add({Mesh,Mesh->GetStaticMesh(),uint8(Mesh->Mobility)});
    }
    if(Entries.Num()==0 || Meshes.Num()==0) {Error=TEXT("没有匹配到停车车辆分离资源。");return false;}
    return true;
}
void UGHSOrderReplaySession::CaptureAndIsolate()
{
    Originals.Reset();Instances.Reset();bCaptured=true;bRestoreVerified=false;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner()))
    {
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn())) {CameraPose=Camera->CaptureReplayPose();Camera->FreezeCurrentPose();}
        if(PC->WarehouseRoof) {RoofTransition=PC->WarehouseRoof->CaptureReplayState();bSavedBuilding=PC->WarehouseRoof->IsBuildingVisible();}
    }
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        AActor* Actor=*It;if(Actor==Replay || !EquipmentActor(Actor)) continue;
        FActorState Record;Record.Actor=Actor;Record.Hidden=Actor->IsHidden();Record.Tick=Actor->IsActorTickEnabled();
        for(auto* Component:Actor->GetComponents()) if(Component)
        {Record.Components.Add({Component,Component->IsComponentTickEnabled()});Component->SetComponentTickEnabled(false);}
        Originals.Add(MoveTemp(Record));Actor->SetActorHiddenInGame(true);Actor->SetActorTickEnabled(false);
    }
    FString Text;FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/order-replay-parking.json")));
    const auto Entries=ArrayJson(Text);
    for(auto& Entry:Meshes) if(auto* Mesh=Entry.Component.Get())
        for(int32 I=0;I<Entries.Num();++I)
        {
            FString Source;Entries[I]->AsObject()->TryGetStringField(TEXT("source"),Source);
            if(Entry.Mesh->GetPathName()==Source || Entry.Mesh->GetPathName().StartsWith(Source+TEXT(".")))
            {Mesh->SetMobility(EComponentMobility::Movable);Mesh->SetStaticMesh(ParkingAlternates[I]);break;}
        }
}
bool UGHSOrderReplaySession::HideSourceInstances()
{
    FBox CargoBounds(ForceInit);TArray<FBox> LoadingDoors;
    const auto Sources=ArrayJson(Replay->GetSourceInstancesJson());
    for(const auto& Source:Sources)
    {
        const auto Object=Source->AsObject();FString ActorName,ComponentName;double IndexValue=-1;
        if(!Object.IsValid() || !Object->TryGetStringField(TEXT("actor"),ActorName) || !Object->TryGetStringField(TEXT("component"),ComponentName) || !Object->TryGetNumberField(TEXT("index"),IndexValue))
        {Error=TEXT("回放货位映射无效。");return false;}
        bool Found=false;
        for(TActorIterator<AActor> It(GetWorld());It && !Found;++It)
        {
            if(It->GetName()!=ActorName) continue;
            for(auto* Component:It->GetComponents()) if(Component->GetName()==ComponentName)
                if(auto* ISM=Cast<UInstancedStaticMeshComponent>(Component))
                {
                    const int32 Index=int32(IndexValue);FTransform Transform;
                    if(Index<0 || Index>=ISM->GetInstanceCount() || !ISM->GetInstanceTransform(Index,Transform,false)) break;
                    FString Role;Object->TryGetStringField(TEXT("role"),Role);
                    if(Role==TEXT("cargo")) CargoBounds+=ISM->Bounds.GetBox();
                    else if(Role==TEXT("door") && ISM->GetStaticMesh())
                        LoadingDoors.Add(ISM->GetStaticMesh()->GetBoundingBox().TransformBy(Transform*ISM->GetComponentTransform()));
                    Instances.Add({ISM,Index,Transform});FTransform Hidden=Transform;Hidden.SetScale3D(FVector::ZeroVector);
                    ISM->UpdateInstanceTransform(Index,Hidden,false,true,true);Found=true;break;
                }
        }
        if(!Found) {Error=TEXT("回放货位或月台已变化: ")+ActorName;return false;}
    }
    if(!CargoBounds.IsValid) {Error=TEXT("回放地堆区域没有可用边界。");return false;}
    // The full floor-storage groups define this view. Far-west docks and trucks
    // on public roads remain available through follow but never widen this frame.
    WorkAreaBounds=CargoBounds.ExpandBy(FVector(400,400,0));
    for(const FBox& Door:LoadingDoors)
        if(Door.GetCenter().X>=CargoBounds.Min.X && Door.GetCenter().X<=CargoBounds.Max.X)
            WorkAreaBounds.Max.Y=FMath::Max(WorkAreaBounds.Max.Y,Door.Max.Y+1700.);
    WorkAreaBounds.Min.Z=0;WorkAreaBounds.Max.Z=FMath::Max(450.,WorkAreaBounds.Max.Z);
    return true;
}
void UGHSOrderReplaySession::Restore()
{
    if(!bCaptured) {Meshes.Reset();ParkingAlternates.Reset();return;}
    RestoredActors=RestoredComponents=RestoredInstances=RestoredMeshes=0;bRestoreVerified=true;
    for(const auto& Record:Originals) if(auto* Actor=Record.Actor.Get())
    {
        Actor->SetActorHiddenInGame(Record.Hidden);Actor->SetActorTickEnabled(Record.Tick);++RestoredActors;
        bRestoreVerified&=Actor->IsHidden()==Record.Hidden && Actor->IsActorTickEnabled()==Record.Tick;
        for(const auto& C:Record.Components) if(auto* Component=C.Component.Get()) {Component->SetComponentTickEnabled(C.Tick);++RestoredComponents;bRestoreVerified&=Component->IsComponentTickEnabled()==C.Tick;}
    }
    for(const auto& Record:Instances) if(auto* Component=Record.Component.Get())
    {
        bRestoreVerified&=Component->UpdateInstanceTransform(Record.Index,Record.Transform,false,true,true);
        FTransform Current;Component->GetInstanceTransform(Record.Index,Current,false);bRestoreVerified&=Current.Equals(Record.Transform);++RestoredInstances;
    }
    for(const auto& Record:Meshes) if(auto* Component=Record.Component.Get())
    {Component->SetStaticMesh(Record.Mesh.Get());Component->SetMobility(EComponentMobility::Type(Record.Mobility));bRestoreVerified&=Component->GetStaticMesh()==Record.Mesh.Get() && uint8(Component->Mobility)==Record.Mobility;++RestoredMeshes;}
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner()))
    {
        if(PC->WarehouseRoof) PC->WarehouseRoof->RestoreReplayState(RoofTransition,bSavedBuilding);
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn())) Camera->RestoreReplayPose(CameraPose);
    }
    Originals.Reset();Instances.Reset();Meshes.Reset();ParkingAlternates.Reset();bCaptured=false;
}
void UGHSOrderReplaySession::Stop()
{
    if(Replay) {Replay->Destroy();Replay=nullptr;}
    Restore();bActive=bPreparing=false;Clock.Playing=false;FollowId.Empty();SelectedId.Empty();Exit.Intent.Empty();
}
void UGHSOrderReplaySession::Advance(float Delta,FVector2D Viewport,FVector2D SceneCenter)
{
    if(!bActive || !Replay) return;
    auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner());
    if(bPreparing)
    {
        if(PC && PC->WarehouseRoof && !PC->WarehouseRoof->IsInteriorAvailable()) return;
        bPreparing=false;
    }
    Clock.Advance(Delta);Replay->EvaluateAt(Clock.Time);
    if(!FollowId.IsEmpty() && !Exit.Pending())
    {
        FVector At,Extent;FRotator Rotation;
        if(Replay->ResolveDevice(FollowId,At,Rotation,Extent))
            if(auto* Camera=PC?Cast<AGHSWarehouseCameraPawn>(PC->GetPawn()):nullptr)
            {Camera->UpdateReplayViewport(Viewport,SceneCenter);Camera->FollowReplayTarget(At,Delta);}
    }
}
void UGHSOrderReplaySession::Play() {if(bActive && !Exit.Pending()) {if(Clock.Completed()) Seek(0);Clock.Playing=true;}}
void UGHSOrderReplaySession::Pause() {if(bActive && !Exit.Pending()) Clock.Playing=false;}
void UGHSOrderReplaySession::Seek(double Seconds) {if(bActive && !Exit.Pending()) {Clock.Seek(Seconds);Replay->EvaluateAt(Clock.Time);}}
void UGHSOrderReplaySession::SetRate(double Value) {if(bActive && !Exit.Pending()) Clock.SetRate(Value);}
void UGHSOrderReplaySession::Select(const FString& Id)
{
    FVector P,E;FRotator R;
    if(bActive && !Exit.Pending() && (Id.IsEmpty() || Replay->ResolveDevice(Id,P,R,E)))
    {SelectedId=Id;Replay->SetTrailMode(TrailMode,SelectedId);}
}
void UGHSOrderReplaySession::Follow(const FString& Id,FVector2D Viewport,FVector2D SceneCenter)
{
    if(!bActive || Exit.Pending()) return;
    if(Id.IsEmpty()) {FollowId.Empty();if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner())) if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn())) {Camera->SetReplayFollowEnabled(false);Camera->FreezeCurrentPose();}return;}
    FVector P,E;FRotator R;if(!Replay->ResolveDevice(Id,P,R,E)) return;
    Select(Id);FollowId=Id;
    if(auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner())) if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(PC->GetPawn()))
    {
        Camera->FocusOnTarget(P,Id.Contains(TEXT("TRUCK"))?2800.f:1100.f,FRotator(Id.Contains(TEXT("TRUCK"))?-38:-62,R.Yaw-65,0),Viewport,SceneCenter);
        Camera->SetReplayFollowEnabled(true);
    }
}
void UGHSOrderReplaySession::SetTrails(const FString& Mode)
{if(bActive && (Mode==TEXT("all") || Mode==TEXT("selected") || Mode==TEXT("off"))) {TrailMode=Mode;Replay->SetTrailMode(Mode,SelectedId);}}
void UGHSOrderReplaySession::SetEventWindow(double Start,double End,bool bReset)
{
    ++EventWindowRevision;
    if(bReset) {EventWindowStart=EventWindowEnd=-1;return;}
    if(FMath::IsFinite(Start) && FMath::IsFinite(End) && End>Start)
    {EventWindowStart=FMath::Clamp(Start,0.,Clock.Duration);EventWindowEnd=FMath::Clamp(End,EventWindowStart,Clock.Duration);}
}
bool UGHSOrderReplaySession::Pick(const FVector& Origin,const FVector& Direction,FString& Id) const
{return bActive && !bPreparing && !Exit.Pending() && Replay && Replay->PickRay(Origin,Direction,Id);}
bool UGHSOrderReplaySession::RequestExit(const FString& Intent,const FString& Title,const FString& Label)
{if(!bActive || !Exit.Request(Intent,Clock)) return false;ExitTitle=Title;ExitLabel=Label;return true;}
void UGHSOrderReplaySession::CancelExit() {Exit.Cancel(Clock);}
FString UGHSOrderReplaySession::ConfirmExit()
{if(!Exit.Pending()) return FString();FString Intent=Exit.Consume();Stop();return bRestoreVerified?Intent:FString();}
FString UGHSOrderReplaySession::GetStateJson() const
{
    TSharedPtr<FJsonObject> State=MakeShared<FJsonObject>();
    if(Replay) FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Replay->GetSnapshotJson()),State);
    if(!State.IsValid()) State=MakeShared<FJsonObject>();
    State->SetBoolField(TEXT("active"),bActive);State->SetBoolField(TEXT("preparing"),bPreparing);
    State->SetBoolField(TEXT("playing"),bActive && Clock.Playing);State->SetBoolField(TEXT("completed"),bActive && Clock.Completed());
    State->SetBoolField(TEXT("isTest"),true);State->SetNumberField(TEXT("time"),Clock.Time);State->SetNumberField(TEXT("duration"),Clock.Duration);State->SetNumberField(TEXT("rate"),Clock.Rate);
    State->SetStringField(TEXT("startUtc"),StartUtc);State->SetStringField(TEXT("endUtc"),EndUtc);State->SetStringField(TEXT("orderId"),OrderId);
    State->SetStringField(TEXT("followId"),FollowId);State->SetStringField(TEXT("selectedId"),SelectedId);State->SetStringField(TEXT("trailMode"),TrailMode);
    State->SetStringField(TEXT("error"),Error);State->SetBoolField(TEXT("exitPending"),Exit.Pending());State->SetStringField(TEXT("exitTitle"),ExitTitle);State->SetStringField(TEXT("exitActionLabel"),ExitLabel);
    if(Replay)
    {
        const double Cycle=Replay->GetCycleDuration();State->SetNumberField(TEXT("cycleDuration"),Cycle);
        const double WindowStart=EventWindowStart>=0?EventWindowStart:FMath::Max(0.,Clock.Time-300.);
        const double WindowEnd=EventWindowEnd>=0?EventWindowEnd:FMath::Min(Clock.Duration,Clock.Time+900.);
        const auto CycleEvents=ArrayJson(Replay->GetEventsJson(0,Cycle-.000001,4096));
        const auto CountEvents=[&](double A,double B)
        {
            double Count=0;
            for(const auto& Event:CycleEvents)
            {
                const double T=Event->AsObject()->GetNumberField(TEXT("time"));
                const double First=FMath::Max(0.,FMath::CeilToDouble((A-T)/Cycle));
                const double Last=FMath::FloorToDouble((B-T)/Cycle);
                Count+=FMath::Max(0.,Last-First+1);
            }
            return Count;
        };
        State->SetArrayField(TEXT("events"),ArrayJson(Replay->GetEventsJson(WindowStart,WindowEnd,100)));
        if(EventWindowStart>=0)
        {auto Window=MakeShared<FJsonObject>();Window->SetNumberField(TEXT("start"),WindowStart);Window->SetNumberField(TEXT("end"),WindowEnd);Window->SetNumberField(TEXT("total"),CountEvents(WindowStart,WindowEnd));Window->SetNumberField(TEXT("revision"),double(EventWindowRevision));State->SetObjectField(TEXT("eventsWindow"),Window);}
        // Bounded interval bins: one representative plus an aggregate count per occupied bin.
        constexpr int32 Bins=96;
        if(CachedMarkers.IsEmpty()) for(int32 I=0;I<Bins;++I)
        {
            const double A=Clock.Duration*I/Bins,B=Clock.Duration*(I+1)/Bins;
            auto Events=ArrayJson(Replay->GetEventsJson(A,B-.000001,256));
            if(Events.Num())
            {
                auto Marker=Events[0]->AsObject();
                for(const auto& Event:Events) {FString Type;Event->AsObject()->TryGetStringField(TEXT("type"),Type);if(Type==TEXT("fault")) {Marker=Event->AsObject();break;}}
                const double Count=CountEvents(A,B-.000001);
                Marker->SetNumberField(TEXT("count"),Count);Marker->SetBoolField(TEXT("aggregated"),Count>1);Marker->SetNumberField(TEXT("rangeStart"),A);Marker->SetNumberField(TEXT("rangeEnd"),B);CachedMarkers.Add(MakeShared<FJsonValueObject>(Marker));
            }
        }
        State->SetArrayField(TEXT("markers"),CachedMarkers);
    }
    return WriteSessionJson(State.ToSharedRef());
}
FString UGHSOrderReplaySession::GetRestorationReport() const
{
    auto Result=MakeShared<FJsonObject>();Result->SetBoolField(TEXT("verified"),bRestoreVerified);
    Result->SetNumberField(TEXT("actors"),RestoredActors);Result->SetNumberField(TEXT("components"),RestoredComponents);
    Result->SetNumberField(TEXT("instances"),RestoredInstances);Result->SetNumberField(TEXT("meshes"),RestoredMeshes);
    Result->SetBoolField(TEXT("active"),bActive);Result->SetBoolField(TEXT("replayActorExists"),IsValid(Replay));return WriteSessionJson(Result);
}
