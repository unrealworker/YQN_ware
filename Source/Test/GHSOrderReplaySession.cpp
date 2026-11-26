#include "GHSOrderReplaySession.h"
#include "GHSOrderReplayActor.h"
#include "GHSStorageCapacityComponent.h"
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
#include "Misc/SecureHash.h"
THIRD_PARTY_INCLUDES_START
#include <openssl/sha.h>
THIRD_PARTY_INCLUDES_END

namespace
{
FString WriteSessionJson(const TSharedRef<FJsonObject>& Object)
{FString Out;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Out));return Out;}
TArray<TSharedPtr<FJsonValue>> ArrayJson(const FString& Text)
{TArray<TSharedPtr<FJsonValue>> Values;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Values);return Values;}
bool ReadReplayVector(const FJsonObject& Object,const TCHAR* Field,FVector& Vector)
{
    const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;
    if(!Object.TryGetArrayField(Field,Values) || Values->Num()!=3) return false;
    for(int32 Axis=0;Axis<3;++Axis)
        if(!(*Values)[Axis]->TryGetNumber(Vector[Axis]) || !FMath::IsFinite(Vector[Axis])) return false;
    return true;
}

bool ReadReplayRegistry(const FString& Hash,TSharedPtr<FJsonObject>& Registry,FString& Error)
{
    TArray<uint8> Bytes;
    if(!FFileHelper::LoadFileToArray(Bytes,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/scene-bindings.json"))))
    {Error=TEXT("无法读取追溯所需的场景实例清单。");return false;}
    if(!Hash.IsEmpty())
    {
        uint8 Digest[SHA256_DIGEST_LENGTH];
        if(!SHA256(Bytes.GetData(),Bytes.Num(),Digest) || !BytesToHex(Digest,SHA256_DIGEST_LENGTH).Equals(Hash,ESearchCase::IgnoreCase))
        {Error=TEXT("追溯路径与当前 CAD 布局版本不一致。");return false;}
    }
    FString Text;
    FFileHelper::BufferToString(Text,Bytes.GetData(),Bytes.Num());
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Registry) || !Registry)
    {Error=TEXT("场景实例清单格式无效。");return false;}
    if(Hash.IsEmpty() && Registry->HasField(TEXT("rackSourceSha256")))
    {Error=TEXT("当前 CAD 布局需要按 CAD 标识绑定的追溯路径。");return false;}
    return true;
}

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

bool GHSReplaySources::Resolve(const FJsonObject& Source,const FJsonObject& Registry,
    const TArray<UInstancedStaticMeshComponent*>& Components,UInstancedStaticMeshComponent*& OutComponent,int32& OutIndex)
{
    OutComponent=nullptr;OutIndex=INDEX_NONE;
    FString Id,Role;
    FVector Position,Scale;
    double Yaw;
    if(!Source.TryGetStringField(TEXT("cadId"),Id) || !Id.StartsWith(TEXT("CAD_"))
        || !Source.TryGetStringField(TEXT("role"),Role) || (Role!=TEXT("cargo") && Role!=TEXT("door") && Role!=TEXT("rackSlot"))
        || !ReadReplayVector(Source,TEXT("position"),Position) || !ReadReplayVector(Source,TEXT("scale"),Scale)
        || !Source.TryGetNumberField(TEXT("yaw"),Yaw) || !FMath::IsFinite(Yaw)) return false;
    const TArray<TSharedPtr<FJsonValue>>* Groups=nullptr;
    if(!Registry.TryGetArrayField(TEXT("groups"),Groups)) return false;
    FString MeshName,GroupName;
    for(const auto& Value:*Groups)
    {
        const auto Group=Value->AsObject();
        FString Mesh,Actor;
        const TArray<TSharedPtr<FJsonValue>>* Entries=nullptr;
        if(!Group || !Group->TryGetStringField(TEXT("mesh"),Mesh) || !Group->TryGetStringField(TEXT("actor"),Actor)
            || !Group->TryGetArrayField(TEXT("instances"),Entries)) continue;
        if((Role==TEXT("door") && Mesh!=TEXT("SM_GHS_V2DockDoor"))
            || (Role==TEXT("cargo") && !Mesh.StartsWith(TEXT("SM_GHS_Presentation_Cargo")))
            || (Role==TEXT("rackSlot") && !Mesh.StartsWith(TEXT("SM_GHS_V2Rack_CAD24_")))) continue;
        for(const auto& Entry:*Entries)
        {
            const auto Row=Entry->AsObject();
            FString CadId;
            if(!Row || !Row->TryGetStringField(TEXT("id"),CadId) || CadId!=Id) continue;
            FVector Cad;
            if(!MeshName.IsEmpty() || !ReadReplayVector(*Row,TEXT("position_m"),Cad)
                || !Position.Equals(FVector(Cad.X*100,-Cad.Y*100,Cad.Z*100),.15)) return false;
            if(Role!=TEXT("door"))
            {
                double CadYaw;
                FVector CadScale;
                if(!Row->TryGetNumberField(TEXT("rotation_deg"),CadYaw) || !ReadReplayVector(*Row,TEXT("scale"),CadScale)
                    || FMath::Abs(FMath::FindDeltaAngleDegrees(-CadYaw,Yaw))>.05 || !Scale.Equals(CadScale,.001)) return false;
            }
            MeshName=Role==TEXT("rackSlot")?Mesh+TEXT("_Capacity"):Mesh;
            GroupName=Actor;
        }
    }
    if(MeshName.IsEmpty()) return false;
    const FQuat Rotation=FRotator(0,Yaw,0).Quaternion();
    UInstancedStaticMeshComponent* Found=nullptr;
    int32 Index=INDEX_NONE;
    for(auto* Component:Components)
    {
        if(!Component || !Component->GetStaticMesh() || Component->GetStaticMesh()->GetName()!=MeshName) continue;
        if(Role!=TEXT("door") && !Component->ComponentHasTag(FName(TEXT("GHSStorageGroup:")+GroupName))) continue;
        for(int32 I=0;I<Component->GetInstanceCount();++I)
        {
            FTransform Actual;
            if(!Component->GetInstanceTransform(I,Actual,true) || !Actual.GetLocation().Equals(Position,.15)
                || !Actual.GetScale3D().Equals(Scale,.001) || !Actual.GetRotation().Equals(Rotation,.0005)) continue;
            if(Found) return false;
            Found=Component;Index=I;
        }
    }
    OutComponent=Found;OutIndex=Index;
    return Found!=nullptr;
}

bool FGHSReplayClock::Start(double Seconds)
{
    if(!FMath::IsFinite(Seconds) || Seconds<3600) return false;
    Time=TrailTime=0;Duration=Seconds;Rate=1;Playing=true;return true;
}
void FGHSReplayClock::Advance(double Seconds)
{
    if(!Playing || !FMath::IsFinite(Seconds) || Seconds<=0) return;
    const double NextTime=FMath::Min(Duration,Time+Seconds*Rate);
    // Fast transport moves the task cursor immediately. The directional dashes
    // advance in viewing time so they remain readable even at 64x.
    TrailTime+=(NextTime-Time)/Rate;
    Time=NextTime;if(Completed()) Playing=false;
}
void FGHSReplayClock::Seek(double Seconds)
{if(FMath::IsFinite(Seconds)) {Time=TrailTime=FMath::Clamp(Seconds,0.,Duration);if(Completed()) Playing=false;}}
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
    Replay->EvaluateAt(0,0);Replay->SetTrailMode(TrailMode,SelectedId);
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
    Originals.Reset();Instances.Reset();RackSlots.Reset();bCaptured=true;bRestoreVerified=false;
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
    const FString& Hash=Replay->GetSceneBindingsHash();
    TSharedPtr<FJsonObject> Registry;
    if(!ReadReplayRegistry(Hash,Registry,Error)) return false;
    TArray<UInstancedStaticMeshComponent*> Components;
    for(TActorIterator<AActor> It(GetWorld());It;++It)
    {
        TInlineComponentArray<UInstancedStaticMeshComponent*> OnActor(*It);
        for(UInstancedStaticMeshComponent* Component:OnActor) Components.Add(Component);
    }
    TArray<FInstanceState> Resolved;
    TArray<FRackSlotState> SlotSources;
    TSet<FString> RackCargoIds;
    auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner());
    auto* Capacity=PC?PC->StorageCapacity.Get():nullptr;
    int32 DoorCount=0,GroundCount=0;
    for(const auto& Source:Sources)
    {
        const auto Object=Source->AsObject();
        FString Role,CadId;
        if(!Object || !Object->TryGetStringField(TEXT("role"),Role) || (Role!=TEXT("cargo") && Role!=TEXT("door") && Role!=TEXT("rackSlot")))
        {Error=TEXT("追溯文件包含无效的实例类型。");return false;}
        UInstancedStaticMeshComponent* Component=nullptr;
        int32 Index=INDEX_NONE;
        if(!Hash.IsEmpty())
        {
            Object->TryGetStringField(TEXT("cadId"),CadId);
            if(!GHSReplaySources::Resolve(*Object,*Registry,Components,Component,Index))
            {Error=TEXT("追溯 CAD 实例缺失、重复或姿态已变化：")+CadId;return false;}
        }
        else
        {
            FString ActorName,ComponentName;
            if(Object->TryGetStringField(TEXT("actor"),ActorName) && Object->TryGetStringField(TEXT("component"),ComponentName)
                && Object->TryGetNumberField(TEXT("index"),Index))
                for(auto* Candidate:Components)
                    if(Candidate->GetOwner()->GetName()==ActorName && Candidate->GetName()==ComponentName)
                    {Component=Candidate;break;}
        }
        FTransform Transform;
        if(!Component || !Component->GetStaticMesh() || Index<0 || Index>=Component->GetInstanceCount() ||
            !Component->GetInstanceTransform(Index,Transform,false) || Resolved.ContainsByPredicate([&](const FInstanceState& State)
                {return State.Component.Get()==Component && State.Index==Index;}))
        {Error=TEXT("追溯引用缺失或指向同一场景实例：")+CadId;return false;}
        if(Role==TEXT("rackSlot"))
        {
            FString LocationId,LocationCode;
            int32 Level=0,Column=0,Slot=INDEX_NONE;
            FBox Bounds(ForceInit);
            if(Hash.IsEmpty() || !Capacity || !Object->TryGetStringField(TEXT("locationId"),LocationId)
                || !Object->TryGetStringField(TEXT("locationCode"),LocationCode) || !Object->TryGetNumberField(TEXT("level"),Level)
                || !Object->TryGetNumberField(TEXT("column"),Column) || !Capacity->InitializeForWorld()
                || !Capacity->ResolveReplaySlot(Component,Index,CadId,Level,Column,LocationId,LocationCode,Slot,Bounds))
            {Error=TEXT("货架取货位未匹配当前有货库位：")+CadId+TEXT(" / ")+LocationCode;return false;}
            if(SlotSources.ContainsByPredicate([&](const FRackSlotState& SourceSlot)
                {return SourceSlot.Component.Get()==Component && SourceSlot.Instance==Index && SourceSlot.Slot==Slot;}))
            {Error=TEXT("货架取货位重复：")+LocationCode;return false;}
            FString CargoId;
            FVector PalletBase=Bounds.GetCenter();
            PalletBase.Z=Bounds.Min.Z;
            bool bCargoAtSlot=false;
            if(Object->TryGetStringField(TEXT("cargoId"),CargoId) && !RackCargoIds.Contains(CargoId))
            {
                for(const auto& Track:Replay->GetSimulation().Tracks)
                {
                    if(Track.Kind!="cargo" || FString(UTF8_TO_TCHAR(Track.Id.c_str()))!=CargoId || Track.Keys.empty()) continue;
                    const auto& Initial=Track.Keys.front();
                    const auto& P=Initial.Position;
                    bCargoAtSlot=Initial.Time==0 && Initial.Visible && Initial.Owner==-1 && FVector(P.X,P.Y,P.Z).Equals(PalletBase,.15);
                    break;
                }
            }
            if(!bCargoAtSlot) {Error=TEXT("回放托盘的起点未匹配货架取货位：")+LocationCode;return false;}
            RackCargoIds.Add(CargoId);
            SlotSources.Add({Component,Index,Slot});
            CargoBounds+=Bounds;
            continue;
        }
        if(Role==TEXT("cargo")) {++GroundCount;CargoBounds+=Component->Bounds.GetBox();}
        else {++DoorCount;LoadingDoors.Add(Component->GetStaticMesh()->GetBoundingBox().TransformBy(Transform*Component->GetComponentTransform()));}
        Resolved.Add({Component,Index,Transform});
    }
    if(!CargoBounds.IsValid || 2*GroundCount+SlotSources.Num()!=GHSReplay::CargoCount || DoorCount!=GHSReplay::TruckCount)
    {Error=TEXT("回放取货托盘或月台数量与路径不一致。");return false;}
    for(const FInstanceState& Record:Resolved)
    {
        FTransform Hidden=Record.Transform;Hidden.SetScale3D(FVector::ZeroVector);
        if(!Record.Component->UpdateInstanceTransform(Record.Index,Hidden,false,true,true))
        {Error=TEXT("回放实例无法隐藏，已取消本次追溯。");return false;}
        Instances.Add(Record);
    }
    for(const auto& Record:SlotSources)
    {
        if(!Capacity->SetReplaySlotHidden(Record.Component.Get(),Record.Instance,Record.Slot,true))
        {Error=TEXT("无法分离货架托位，已取消本次追溯。");return false;}
        RackSlots.Add(Record);
    }
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
    RestoredActors=RestoredComponents=RestoredInstances=RestoredMeshes=RestoredRackSlots=0;bRestoreVerified=true;
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
    auto* PC=Cast<AGHSWarehousePlayerController>(GetOwner());
    for(const auto& Record:RackSlots)
    {
        if(PC && PC->StorageCapacity && PC->StorageCapacity->SetReplaySlotHidden(Record.Component.Get(),Record.Instance,Record.Slot,false))
            ++RestoredRackSlots;
        else bRestoreVerified=false;
    }
    RackSlots.Reset();
    if(PC)
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
    Clock.Advance(Delta);Replay->EvaluateAt(Clock.Time,Clock.TrailTime);
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
void UGHSOrderReplaySession::Seek(double Seconds) {if(bActive && !Exit.Pending()) {Clock.Seek(Seconds);Replay->EvaluateAt(Clock.Time,Clock.TrailTime);}}
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
    Result->SetNumberField(TEXT("rackSlots"),RestoredRackSlots);
    Result->SetBoolField(TEXT("active"),bActive);Result->SetBoolField(TEXT("replayActorExists"),IsValid(Replay));return WriteSessionJson(Result);
}
