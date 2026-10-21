#include "GHSTwinSceneData.h"

#include "GHSDockTruckDataComponent.h"
#include "GHSMannedForkliftDataComponent.h"
#include "GHSMannedForkliftIdentityLibrary.h"
#include "GHSStackerDataComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "InstancedStaticMeshDelegates.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    bool PositiveNumber(const FString& Text, int32& Out)
    {
        if (Text.IsEmpty()) return false;
        int32 Number = 0;
        for (const TCHAR C : Text)
        {
            if (C < TEXT('0') || C > TEXT('9')) return false;
            const int32 Digit = C - TEXT('0');
            if (Number > (MAX_int32 - Digit) / 10) return false;
            Number = Number * 10 + Digit;
        }
        if (Number == 0) return false;
        Out = Number;
        return true;
    }

    bool SingleTag(const TArray<FName>& Tags, const TCHAR* Prefix, FString& Out)
    {
        bool bFound = false;
        Out.Empty();
        for (const FName Tag : Tags)
        {
            const FString Text = Tag.ToString();
            if (!Text.StartsWith(Prefix, ESearchCase::CaseSensitive)) continue;
            if (bFound) { Out.Empty(); return false; }
            bFound = true;
            Out = Text.Mid(FCString::Strlen(Prefix));
        }
        return bFound;
    }

    TSharedPtr<FJsonObject> ReadJson(const FString& Path)
    {
        FString Text;
        TSharedPtr<FJsonObject> Result;
        if (FFileHelper::LoadFileToString(Text, *Path))
            FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Result);
        return Result;
    }

    bool JsonVector(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, FVector& Out)
    {
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!Object.IsValid() || !Object->TryGetArrayField(Key, Values) || Values->Num() != 3) return false;
        double X, Y, Z;
        if (!(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y) || !(*Values)[2]->TryGetNumber(Z)) return false;
        Out = FVector(X,Y,Z);
        return !Out.ContainsNaN();
    }

    void SetVector(const TSharedRef<FJsonObject>& Object, const TCHAR* Key, const FVector& Position)
    {
        Object->SetArrayField(Key, {
            MakeShared<FJsonValueNumber>(Position.X), MakeShared<FJsonValueNumber>(Position.Y), MakeShared<FJsonValueNumber>(Position.Z)});
    }

    FString EnumState(uint8 State)
    {
        // Forklift and stacker enums share their documented state ordering.
        switch (State)
        {
        case 1: return TEXT("running");
        case 2: return TEXT("idle");
        case 3: return TEXT("warning");
        case 4: return TEXT("fault");
        case 5: return TEXT("offline");
        default: return TEXT("unknown");
        }
    }
}

bool GHSTwinSelection::Identify(const TArray<FName>& Tags, FIdentity& Out)
{
    Out = FIdentity();
    FString Twin;
    if (!SingleTag(Tags, TEXT("TwinId="), Twin)) return false;
    struct FKind { const TCHAR* Prefix; const TCHAR* RequiredTag; const TCHAR* IdPrefix; const TCHAR* Type; const TCHAR* Title; int32 Digits; };
    static const FKind Kinds[] = {
        {TEXT("GHS_DockTruck_"),TEXT("IndependentDockTruck"),TEXT("TRUCK-"),TEXT("truck"),TEXT("装卸车辆"),3},
        {TEXT("GHN_MannedForklift_"),TEXT("NormalWarehouseMannedForklift"),TEXT("FORK-"),TEXT("forklift"),TEXT("人工叉车"),2},
        {TEXT("GHN_FloorStacker_"),TEXT("NormalWarehouseFloorStacker"),TEXT("STACKER-"),TEXT("stacker"),TEXT("电动堆高车"),2},
        {TEXT("GHS_AGV_"),nullptr,TEXT("AGV-"),TEXT("agv"),TEXT("AGV 搬运机器人"),2},
        {TEXT("GHS_CH_"),nullptr,TEXT("CH-"),TEXT("charger"),TEXT("充电设施"),2}
    };
    for (const FKind& Kind : Kinds)
    {
        if (!Twin.StartsWith(Kind.Prefix,ESearchCase::CaseSensitive)) continue;
        int32 Number = 0;
        if ((Kind.RequiredTag && !Tags.Contains(FName(Kind.RequiredTag)))
            || !PositiveNumber(Twin.Mid(FCString::Strlen(Kind.Prefix)),Number)) return false;
        FString DockId;
        if (FCString::Strcmp(Kind.Type,TEXT("truck")) == 0)
        {
            FString Dock;
            int32 DockNumber = 0;
            if (!SingleTag(Tags,TEXT("Dock="),Dock) || !PositiveNumber(Dock,DockNumber)) return false;
            DockId = FString::Printf(TEXT("DOCK-%02d"),DockNumber);
        }
        Out.Id = FString(Kind.IdPrefix) + FString::Printf(TEXT("%0*d"),Kind.Digits,Number);
        Out.Type = Kind.Type; Out.Title = Kind.Title; Out.DockId = DockId;
        return true;
    }
    return false;
}

namespace
{
int32 BootstrapActors(UWorld* World,const TArray<AActor*>& Actors)
{
    if (!IsValid(World) || !World->IsGameWorld()) return 0;
    UGHSMannedForkliftIdentityLibrary::ReconcileActors(World,Actors);
    int32 Created=0;
    for (AActor* Actor : Actors)
    {
        if (!IsValid(Actor) || Actor->IsActorBeingDestroyed()) continue;
        GHSTwinSelection::FIdentity Identity;
        if (!GHSTwinSelection::Identify(Actor->Tags,Identity)) continue;
        if (Identity.Type==TEXT("forklift"))
        {
            if (!UGHSMannedForkliftIdentityLibrary::IsSupportedActor(Actor)) continue;
            auto* Data=Actor->FindComponentByClass<UGHSMannedForkliftDataComponent>();
            if (Data)
            {
                Data->InitializeFromActorTags();
                continue;
            }
            Data=NewObject<UGHSMannedForkliftDataComponent>(Actor);
            if (!Data->InitializeFromActorTags()) continue;
            Actor->AddInstanceComponent(Data); Data->RegisterComponent();
            Data->ApplyDemoState(FCString::Atoi(*Data->ForkliftId.Mid(5))-1);
            ++Created;
        }
        else if (Identity.Type==TEXT("stacker"))
        {
            auto* Data=Actor->FindComponentByClass<UGHSStackerDataComponent>();
            if (Data)
            {
                Data->InitializeFromActorTags();
                continue;
            }
            Data=NewObject<UGHSStackerDataComponent>(Actor);
            if (!Data->InitializeFromActorTags()) continue;
            Actor->AddInstanceComponent(Data); Data->RegisterComponent();
            Data->ApplyDemoState(FCString::Atoi(*Data->StackerId.Mid(8))-1);
            ++Created;
        }
        else if (Identity.Type==TEXT("truck"))
        {
            auto* Data=Actor->FindComponentByClass<UGHSDockTruckDataComponent>();
            if (Data)
            {
                Data->InitializeFromActorTags();
                continue;
            }
            Data=NewObject<UGHSDockTruckDataComponent>(Actor);
            if (!Data->InitializeFromActorTags()) continue;
            Actor->AddInstanceComponent(Data); Data->RegisterComponent();
            ++Created;
        }
    }
    return Created;
}
}

int32 GHSTwinSelection::BootstrapComponents(UWorld* World)
{
    if(!IsValid(World) || !World->IsGameWorld()) return 0;
    TArray<AActor*> Actors;
    for(TActorIterator<AActor> It(World);It;++It) Actors.Add(*It);
    return BootstrapActors(World,Actors);
}

bool GHSTwinSelection::IntersectBox(const FVector& Origin, const FVector& Direction,
    const FTransform& Transform, const FBox& LocalBounds, double& OutDistance, FVector* OutLocalHit)
{
    if (Origin.ContainsNaN() || Direction.ContainsNaN() || Transform.ContainsNaN() || !LocalBounds.IsValid
        || LocalBounds.Min.ContainsNaN() || LocalBounds.Max.ContainsNaN()) return false;
    const FVector Scale = Transform.GetScale3D();
    if (FMath::Abs(Scale.X)<1.e-8 || FMath::Abs(Scale.Y)<1.e-8 || FMath::Abs(Scale.Z)<1.e-8) return false;
    const FVector Ray = Direction.GetSafeNormal();
    if (Ray.IsNearlyZero()) return false;
    const FVector LocalOrigin = Transform.InverseTransformPosition(Origin);
    // Preserve length here: normalizing the inverse-transformed ray breaks scaled instances.
    const FVector LocalDirection = Transform.InverseTransformVector(Ray);
    double Near = 0, Far = TNumericLimits<double>::Max();
    for (int32 Axis=0; Axis<3; ++Axis)
    {
        if (LocalBounds.Min[Axis] > LocalBounds.Max[Axis]) return false;
        if (FMath::Abs(LocalDirection[Axis]) < 1.e-12)
        {
            if (LocalOrigin[Axis]<LocalBounds.Min[Axis] || LocalOrigin[Axis]>LocalBounds.Max[Axis]) return false;
            continue;
        }
        double A=(LocalBounds.Min[Axis]-LocalOrigin[Axis])/LocalDirection[Axis];
        double B=(LocalBounds.Max[Axis]-LocalOrigin[Axis])/LocalDirection[Axis];
        if (A>B) Swap(A,B);
        Near=FMath::Max(Near,A); Far=FMath::Min(Far,B);
        if (Near>Far) return false;
    }
    if (!FMath::IsFinite(Near) || Far<0) return false;
    OutDistance=Near;
    if (OutLocalHit) *OutLocalHit=LocalOrigin+LocalDirection*Near;
    return true;
}

struct FGHSTwinSceneData::FImpl
{
    struct FSlot
    {
        int32 Level=0, Column=0;
        FBox Bounds=FBox(ForceInit);
    };
    struct FCadInstance
    {
        FString Id, DockId;
        FVector Position=FVector::ZeroVector;
    };
    struct FRecord
    {
        FString Id, Kind, Type, Title, Status=TEXT("unknown"), LocationText, Metric, Value=TEXT("—"), TaskId;
        FString DockId, CadId, MeshName, ParentId, Reason, DriverId;
        TWeakObjectPtr<AActor> Actor;
        TWeakObjectPtr<UStaticMeshComponent> Component;
        TWeakObjectPtr<UActorComponent> Telemetry;
        FTransform Transform=FTransform::Identity;
        FBox LocalBounds=FBox(ForceInit);
        FVector Center=FVector::ZeroVector, Extent=FVector::ZeroVector;
        int32 InstanceIndex=INDEX_NONE, Level=0, Column=0;
        double Progress=0, LastUpdate=-1;
        bool bLive=false, bDemo=false, bAvailable=false, bAlert=false;
        mutable TSharedPtr<FJsonObject> CachedJson;
        mutable FTransform JsonTransform=FTransform::Identity;
        mutable bool bJsonHidden=false;
    };
    struct FVisibility
    {
        TWeakObjectPtr<AActor> Actor;
        bool bOriginalHidden=false;
        bool bEquipment=false;
    };
    struct FStorageCache
    {
        TWeakObjectPtr<UStaticMesh> Mesh;
        FBox LocalBounds=FBox(ForceInit);
        int32 Count=0;
        int32 Cursor=0, LeafCount=1;
        bool bRack=false, bDock=false;
        TArray<FString> Ids;
        TArray<FTransform> Transforms;
        TArray<FBox> BoundsTree;
        void SetBounds(int32 Index,const FBox& Bounds)
        {
            int32 Node=LeafCount+Index; BoundsTree[Node]=Bounds;
            while(Node>1) { Node/=2; BoundsTree[Node]=BoundsTree[Node*2]+BoundsTree[Node*2+1]; }
        }
        FBox Bounds() const { return BoundsTree.Num()>1?BoundsTree[1]:FBox(ForceInit); }
    };
    struct FActorRegistration
    {
        TArray<FName> Tags;
        TSet<TWeakObjectPtr<UActorComponent>> Components;
        GHSTwinSelection::FIdentity Identity;
        TWeakObjectPtr<UStaticMeshComponent> DeviceComponent;
        TWeakObjectPtr<UStaticMesh> DeviceMesh;
        FBox DeviceBounds=FBox(ForceInit);
        TWeakObjectPtr<UActorComponent> Telemetry;
        TArray<TWeakObjectPtr<UInstancedStaticMeshComponent>> Storage;
        bool bDirty=true, bFx=false, bDeviceRegistered=false;
    };

    TWeakObjectPtr<UWorld> World;
    FString MapName;
    TMap<FString,FRecord> Records;
    TArray<FRecord> Devices;
    TMap<FString,int32> DeviceById;
    TMap<FString,FRecord> MaterialSelections;
    TMap<FString,TArray<FCadInstance>> CadByMesh;
    TMap<FString,TArray<FSlot>> SlotsByMesh;
    TMap<TWeakObjectPtr<UInstancedStaticMeshComponent>,FStorageCache> StorageCaches;
    TArray<FVisibility> Visibility;
    TSet<TWeakObjectPtr<AActor>> VisibilityTracked;
    TMap<TWeakObjectPtr<AActor>,FActorRegistration> RegisteredActors;
    TArray<TWeakObjectPtr<UInstancedStaticMeshComponent>> StorageOrder;
    FDelegateHandle SpawnHandle,DestroyedHandle,RemovedHandle,RegisteredHandle,LevelsHandle,InstanceHandle;
    int32 StorageCursor=0;
    double NextWorldValidation=0;
    bool bWorldRescan=true, bBootstrapNeeded=true, bSnapshotDirty=true;
    FString CachedSnapshotBase, LastSentSnapshot;
    TSharedPtr<FJsonObject> CachedSelectionObject;
    FString CachedSelectionJson;
    bool bHasSentSnapshot=false;
    bool bLegacyBootstrapped=false;
    uint64 Revision=0;
    FGHSTwinSceneCacheStats Stats;
    bool bMetadataLoaded=false, bEquipmentVisible=true, bRacksVisible=true;
    int32 RackInstanceCount=0;
    FBox RackRegion=FBox(ForceInit), FloorRegion=FBox(ForceInit);

    void RestoreVisibility()
    {
        for (const FVisibility& Item : Visibility)
            if (Item.Actor.IsValid()) Item.Actor->SetActorHiddenInGame(Item.bOriginalHidden);
        Visibility.Reset();
        VisibilityTracked.Reset();
    }

    void TrackVisibility(AActor* Actor, bool bEquipment)
    {
        if (!Actor || !World.IsValid() || !World->IsGameWorld()) return;
        if (VisibilityTracked.Contains(Actor)) return;
        VisibilityTracked.Add(Actor);
        Visibility.Add({Actor,Actor->IsHidden(),bEquipment});
    }

    void UpdateLayers()
    {
        if (!World.IsValid() || !World->IsGameWorld()) return;
        for (const FVisibility& Item : Visibility)
            if (Item.Actor.IsValid()) Item.Actor->SetActorHiddenInGame(Item.bOriginalHidden || !(Item.bEquipment?bEquipmentVisible:bRacksVisible));
    }

    void AddActor(AActor* Actor)
    {
        if(!IsValid(Actor) || Actor->GetWorld()!=World.Get() || Actor->IsActorBeingDestroyed()) return;
        RegisteredActors.FindOrAdd(Actor).bDirty=true; bBootstrapNeeded=true;
    }
    void RemoveActor(AActor* Actor)
    {
        RegisteredActors.Remove(Actor); bBootstrapNeeded=true; bSnapshotDirty=true;
    }
    void Detach()
    {
        if(auto* W=World.Get())
        {
            W->RemoveOnActorSpawnedHandler(SpawnHandle); W->RemoveOnActorDestroyededHandler(DestroyedHandle);
            W->RemoveOnActorRemovedFromWorldHandler(RemovedHandle);
            W->RemoveOnPostRegisterAllActorComponentsHandler(RegisteredHandle); W->OnLevelsChanged().Remove(LevelsHandle);
        }
        FInstancedStaticMeshDelegates::OnInstanceIndexUpdated.Remove(InstanceHandle);
    }
    void Attach(UWorld* W)
    {
        SpawnHandle=W->AddOnActorSpawnedHandler(FOnActorSpawned::FDelegate::CreateRaw(this,&FImpl::AddActor));
        DestroyedHandle=W->AddOnActorDestroyedHandler(FOnActorDestroyed::FDelegate::CreateRaw(this,&FImpl::RemoveActor));
        RemovedHandle=W->AddOnActorRemovedFromWorldHandler(FOnActorRemovedFromWorld::FDelegate::CreateRaw(this,&FImpl::RemoveActor));
        RegisteredHandle=W->AddOnPostRegisterAllActorComponentsHandler(FOnPostRegisterAllActorComponents::FDelegate::CreateRaw(this,&FImpl::AddActor));
        LevelsHandle=W->OnLevelsChanged().AddLambda([this](){ bWorldRescan=true; });
        InstanceHandle=FInstancedStaticMeshDelegates::OnInstanceIndexUpdated.AddLambda(
            [this](UInstancedStaticMeshComponent* Component,TArrayView<const FInstancedStaticMeshDelegates::FInstanceIndexUpdateData>)
            {
                if(Component && Component->GetWorld()==World.Get())
                {
                    if(auto* Registration=RegisteredActors.Find(Component->GetOwner())) Registration->bDirty=true;
                }
            });
    }
    void Discover()
    {
        ++Stats.WorldScans;
        TSet<TWeakObjectPtr<AActor>> Seen;
        for(TActorIterator<AActor> It(World.Get());It;++It)
        {
            AActor* Actor=*It;
            if(!IsValid(Actor) || Actor->IsActorBeingDestroyed()) continue;
            Seen.Add(Actor);
            if(!RegisteredActors.Contains(Actor)) AddActor(Actor);
        }
        for(auto It=RegisteredActors.CreateIterator();It;++It)
            if(!Seen.Contains(It.Key())) { It.RemoveCurrent(); bBootstrapNeeded=true; bSnapshotDirty=true; }
        bWorldRescan=false; NextWorldValidation=FPlatformTime::Seconds()+30.;
    }
    bool InspectActor(AActor* Actor,FActorRegistration& R)
    {
        ++Stats.ActorsInspected;
        bool bComponentsChanged=R.Components.Num()!=Actor->GetComponents().Num();
        if(!bComponentsChanged)
            for(auto* Component:Actor->GetComponents())
                if(!R.Components.Contains(Component)) { bComponentsChanged=true; break; }
        UStaticMesh* DeviceMesh=R.DeviceComponent.IsValid()?R.DeviceComponent->GetStaticMesh():nullptr;
        // Identity can be edited directly on a data component without changing the actor's
        // tags or component set. Keep the legacy repair contract for that path as well.
        bool bIdentityMismatch=false;
        if(auto* TruckData=Cast<UGHSDockTruckDataComponent>(R.Telemetry.Get()))
            bIdentityMismatch=TruckData->TruckId!=R.Identity.Id || TruckData->DockId!=R.Identity.DockId;
        else if(auto* ForkliftData=Cast<UGHSMannedForkliftDataComponent>(R.Telemetry.Get())) bIdentityMismatch=ForkliftData->ForkliftId!=R.Identity.Id;
        else if(auto* StackerData=Cast<UGHSStackerDataComponent>(R.Telemetry.Get())) bIdentityMismatch=StackerData->StackerId!=R.Identity.Id;
        const bool bChanged=R.bDirty || R.Tags!=Actor->Tags || bComponentsChanged
            || DeviceMesh!=R.DeviceMesh.Get() || (DeviceMesh && !R.DeviceBounds.Equals(DeviceMesh->GetBoundingBox()))
            || bIdentityMismatch || (R.DeviceComponent.IsValid() && R.DeviceComponent->IsRegistered()!=R.bDeviceRegistered);
        if(!bChanged) return false;
        bBootstrapNeeded=true; R.bDirty=false; R.Tags=Actor->Tags;
        R.Components.Reset();
        for(auto* Component:Actor->GetComponents()) R.Components.Add(Component);
        GHSTwinSelection::Identify(Actor->Tags,R.Identity);
        R.DeviceComponent.Reset(); R.DeviceMesh.Reset(); R.Telemetry.Reset(); R.Storage.Reset();
        R.bDeviceRegistered=false;
        // Track even an unclassified or meshless component so a later mesh assignment
        // can make it eligible for legacy identity reconciliation without a world scan.
        auto* Component=Actor->FindComponentByClass<UStaticMeshComponent>();
        if(Component && !Cast<UInstancedStaticMeshComponent>(Component))
        {
            R.DeviceComponent=Component; R.DeviceMesh=Component->GetStaticMesh();
            R.DeviceBounds=R.DeviceMesh.IsValid()?R.DeviceMesh->GetBoundingBox():FBox(ForceInit);
            R.bDeviceRegistered=Component->IsRegistered();
        }
        if(!R.Identity.Id.IsEmpty())
        {
            if(R.Identity.Type==TEXT("truck")) R.Telemetry=Actor->FindComponentByClass<UGHSDockTruckDataComponent>();
            else if(R.Identity.Type==TEXT("forklift")) R.Telemetry=Actor->FindComponentByClass<UGHSMannedForkliftDataComponent>();
            else if(R.Identity.Type==TEXT("stacker")) R.Telemetry=Actor->FindComponentByClass<UGHSStackerDataComponent>();
        }
        else
        {
            TInlineComponentArray<UInstancedStaticMeshComponent*> Components(Actor);
            for(auto* StorageComponent:Components) R.Storage.Add(StorageComponent);
        }
        FString Owner; R.bFx=SingleTag(Actor->Tags,TEXT("FXOwner="),Owner) || Actor->ActorHasTag(TEXT("AGVAnimatedFX"));
        return true;
    }

    void UpdateRegions()
    {
        RackRegion=FBox(ForceInit); FloorRegion=FBox(ForceInit); RackInstanceCount=0;
        for(const auto& Entry:StorageCaches)
        {
            const auto& Cache=Entry.Value;
            if(Cache.bRack) { RackRegion+=Cache.Bounds(); RackInstanceCount+=Cache.Count; }
            else if(!Cache.bDock) FloorRegion+=Cache.Bounds();
        }
    }
    void UpdateInstance(UInstancedStaticMeshComponent* Component,FStorageCache& Cache,int32 Index,const FTransform& Transform)
    {
        const FString OldId=Cache.Ids[Index];
        FRecord Record;
        AActor* Actor=Component->GetOwner(); UStaticMesh* Mesh=Component->GetStaticMesh();
        Record.Id=FString::Printf(TEXT("%s:%s:%s:%d"),Cache.bRack?TEXT("RACK"):TEXT("PALLET"),*Actor->GetName(),*Component->GetName(),Index);
        Record.Kind=Cache.bRack?TEXT("rack"):TEXT("material"); Record.Type=Cache.bRack?TEXT("rack"):TEXT("pallet");
        Record.Title=Cache.bRack?TEXT("实际货架"):TEXT("地堆托盘"); Record.Status=TEXT("scene");
        Record.Actor=Actor; Record.Component=Component; Record.InstanceIndex=Index; Record.MeshName=Mesh->GetName();
        Record.Transform=Transform; Record.LocalBounds=Mesh->GetBoundingBox(); Record.LocationText=Cache.bRack?TEXT("货架区"):TEXT("地堆区");
        Record.bAvailable=true; Record.Metric=TEXT("数据绑定"); Record.Value=TEXT("待绑定业务数据");
        const auto* Metadata=CadByMesh.Find(Record.MeshName);
        if(Metadata && Metadata->Num()==Cache.Count && (*Metadata)[Index].Position.Equals(Transform.GetLocation(),.1))
        { Record.CadId=(*Metadata)[Index].Id; if(Cache.bDock) Record.Id=(*Metadata)[Index].DockId; }
        Cache.Transforms[Index]=Transform;
        if(Cache.bDock && !Record.Id.StartsWith(TEXT("DOCK-")))
        { if(!OldId.IsEmpty()) Records.Remove(OldId); Cache.Ids[Index].Empty(); Cache.SetBounds(Index,FBox(ForceInit)); return; }
        if(Cache.bDock) { Record.Kind=Record.Type=TEXT("dock"); Record.Title=TEXT("装卸月台"); Record.LocationText=Record.Id; }
        UpdateBounds(Record); Cache.SetBounds(Index,Record.LocalBounds.TransformBy(Transform));
        if(!OldId.IsEmpty() && OldId!=Record.Id) Records.Remove(OldId);
        Cache.Ids[Index]=Record.Id; Records.Add(Cache.Ids[Index],MoveTemp(Record)); ++Stats.StorageRecordsBuilt;
    }
    void RebuildStorage(UInstancedStaticMeshComponent* Component,FStorageCache& Cache)
    {
        for(const FString& Id:Cache.Ids) if(!Id.IsEmpty()) Records.Remove(Id);
        Cache=FStorageCache(); Cache.Mesh=Component->GetStaticMesh(); Cache.Count=Component->GetInstanceCount();
        Cache.LocalBounds=Cache.Mesh->GetBoundingBox();
        const FString MeshName=Cache.Mesh->GetName(); Cache.bRack=MeshName.StartsWith(TEXT("SM_GHS_V2Rack_")); Cache.bDock=MeshName==TEXT("SM_GHS_V2DockDoor");
        Cache.Ids.SetNum(Cache.Count); Cache.Transforms.SetNum(Cache.Count);
        while(Cache.LeafCount<Cache.Count) Cache.LeafCount*=2;
        Cache.BoundsTree.Init(FBox(ForceInit),Cache.LeafCount*2);
        for(int32 Index=0;Index<Cache.Count;++Index)
        { FTransform Transform; if(Component->GetInstanceTransform(Index,Transform,true)) UpdateInstance(Component,Cache,Index,Transform); }
        if(!Cache.bDock) TrackVisibility(Component->GetOwner(),false);
        bSnapshotDirty=true;
    }

    void LoadMetadata()
    {
        if (bMetadataLoaded) return;
        bMetadataLoaded=true;
        // Optional source metadata enriches an actual scene binding; geometry remains usable without it.
        auto Registry=ReadJson(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/scene-bindings.json"));
        if (!Registry.IsValid()) Registry=ReadJson(FPaths::ProjectDir()/TEXT("SourceAssets/GHS_Normal/ue_scene_registry.json"));
        const TArray<TSharedPtr<FJsonValue>>* Groups=nullptr;
        if (Registry.IsValid() && Registry->TryGetArrayField(TEXT("groups"),Groups))
        {
            for (const auto& Value : *Groups)
            {
                const auto Group=Value->AsObject();
                FString Mesh;
                const TArray<TSharedPtr<FJsonValue>>* Instances=nullptr;
                if (!Group.IsValid() || !Group->TryGetStringField(TEXT("mesh"),Mesh)
                    || !Group->TryGetArrayField(TEXT("instances"),Instances)
                    || !(Mesh.StartsWith(TEXT("SM_GHS_V2Rack_")) || Mesh.StartsWith(TEXT("SM_GHS_Presentation_Cargo"))
                        || Mesh==TEXT("SM_GHS_V2DockDoor"))) continue;
                auto& Entries=CadByMesh.FindOrAdd(Mesh);
                for (const auto& Item : *Instances)
                {
                    FCadInstance Entry;
                    const auto Object=Item->AsObject();
                    FVector CAD;
                    if (Object.IsValid() && Object->TryGetStringField(TEXT("id"),Entry.Id) && JsonVector(Object,TEXT("position_m"),CAD))
                    {
                        Entry.Position=FVector(CAD.X*100,-CAD.Y*100,CAD.Z*100);
                        FString Dock;
                        int32 Number=0;
                        if (Object->TryGetStringField(TEXT("dock_number"),Dock) && PositiveNumber(Dock,Number))
                            Entry.DockId=FString::Printf(TEXT("DOCK-%02d"),Number);
                    }
                    Entries.Add(MoveTemp(Entry));
                }
            }
        }
        auto Models=ReadJson(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/rack-slots.json"));
        if (!Models.IsValid()) Models=ReadJson(FPaths::ProjectDir()/TEXT("SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json"));
        const TArray<TSharedPtr<FJsonValue>>* Meshes=nullptr;
        if (!Models.IsValid() || !Models->TryGetArrayField(TEXT("meshes"),Meshes)) return;
        for (const auto& Value : *Meshes)
        {
            const auto Model=Value->AsObject();
            FString Name;
            double Width=0,Depth=0;
            const TArray<TSharedPtr<FJsonValue>>* Stacks=nullptr;
            if (!Model.IsValid() || !Model->TryGetStringField(TEXT("name"),Name)
                || !Model->TryGetNumberField(TEXT("cargo_width_m"),Width)
                || !Model->TryGetNumberField(TEXT("cargo_depth_m"),Depth)
                || !Model->TryGetArrayField(TEXT("cargo_stacks"),Stacks) || Width<=0 || Depth<=0) continue;
            auto& Slots=SlotsByMesh.FindOrAdd(Name);
            for (const auto& StackValue : *Stacks)
            {
                const auto Stack=StackValue->AsObject();
                double Level=0,Column=0,Base=0,Top=0,X=0;
                if (!Stack.IsValid() || !Stack->TryGetNumberField(TEXT("level"),Level)
                    || !Stack->TryGetNumberField(TEXT("column"),Column)
                    || !Stack->TryGetNumberField(TEXT("base_z_m"),Base)
                    || !Stack->TryGetNumberField(TEXT("stack_top_z_m"),Top)
                    || !Stack->TryGetNumberField(TEXT("pallet_center_x_m"),X) || Top<=Base) continue;
                FSlot Slot;
                Slot.Level=int32(Level); Slot.Column=int32(Column);
                Slot.Bounds=FBox(FVector((X-Width*.5)*100,-Depth*50,Base*100),FVector((X+Width*.5)*100,Depth*50,Top*100));
                Slots.Add(Slot);
            }
        }
    }

    static void UpdateBounds(FRecord& Record)
    {
        const FBox WorldBounds=Record.LocalBounds.TransformBy(Record.Transform);
        Record.Center=WorldBounds.GetCenter(); Record.Extent=WorldBounds.GetExtent();
    }

    static bool CurrentTransform(const FRecord& Record, FTransform& Out)
    {
        if (!Record.Actor.IsValid() || Record.Actor->IsActorBeingDestroyed() || !Record.Component.IsValid()
            || !Record.Component->IsRegistered() || !Record.Component->GetStaticMesh()) return false;
        if (Record.InstanceIndex!=INDEX_NONE)
        {
            auto* Instances=Cast<UInstancedStaticMeshComponent>(Record.Component.Get());
            return Instances && Instances->GetInstanceTransform(Record.InstanceIndex,Out,true);
        }
        Out=Record.Component->GetComponentTransform();
        return true;
    }

    const FRecord* Find(const FString& Id) const
    {
        auto IsCurrent=[](const FRecord* Record)
        { return Record && Record->Actor.IsValid() && !Record->Actor->IsActorBeingDestroyed()
            && Record->Component.IsValid() && Record->Component->IsRegistered() && Record->Component->GetStaticMesh(); };
        if (const int32* Index=DeviceById.Find(Id))
            return Devices.IsValidIndex(*Index) && IsCurrent(&Devices[*Index])?&Devices[*Index]:nullptr;
        if (const FRecord* Record=Records.Find(Id)) return IsCurrent(Record)?Record:nullptr;
        const FRecord* Material=MaterialSelections.Find(Id);
        return IsCurrent(Material)?Material:nullptr;
    }

    void ReadTelemetry(FRecord& Record)
    {
        AActor* Actor=Record.Actor.Get();
        if (!Actor) return;
        if (Record.Type==TEXT("truck"))
        {
            Record.Metric=TEXT("装载托盘"); Record.LocationText=Record.DockId;
            if (const auto* Data=Cast<UGHSDockTruckDataComponent>(Record.Telemetry.Get()); Data && Data->TruckId==Record.Id)
            {
                switch(Data->Status)
                {
                case EGHSDockTruckStatus::Docked: Record.Status=TEXT("idle"); break;
                case EGHSDockTruckStatus::Loading: Record.Status=TEXT("running"); break;
                case EGHSDockTruckStatus::Warning: Record.Status=TEXT("warning"); break;
                case EGHSDockTruckStatus::Fault: Record.Status=TEXT("fault"); break;
                case EGHSDockTruckStatus::Offline: Record.Status=TEXT("offline"); break;
                default: break;
                }
                Record.bAvailable=Data->HasTelemetry(); Record.bDemo=Data->bIsDemoData;
                Record.LastUpdate=Data->LastUpdateSeconds; Record.TaskId=Data->OrderId;
                Record.Progress=Data->GetLoadingProgress();
                if (Record.bAvailable) Record.Value=FString::Printf(TEXT("%d / %d 托"),Data->LoadedPallets,Data->TotalPallets);
            }
        }
        else if (Record.Type==TEXT("forklift"))
        {
            Record.Metric=TEXT("载荷"); Record.LocationText=TEXT("地堆作业区");
            if (const auto* Data=Cast<UGHSMannedForkliftDataComponent>(Record.Telemetry.Get()); Data && Data->ForkliftId==Record.Id)
            {
                const FString ExpectedOwner=TEXT("GHSManualIdentityOwner=")+Actor->GetName();
                const bool bCopiedOwner=Actor->Tags.ContainsByPredicate([&ExpectedOwner](FName Tag)
                {
                    const FString Value=Tag.ToString();
                    return Value.StartsWith(TEXT("GHSManualIdentityOwner="),ESearchCase::CaseSensitive) && Value!=ExpectedOwner;
                });
                // Reconciliation belongs to the existing identity library. Until it runs, do not
                // expose telemetry inherited by a copied component as data from this vehicle.
                if (bCopiedOwner && !Data->IsIdentityBoundToOwner()) return;
                Record.Status=EnumState(uint8(Data->Status)); Record.bAvailable=Data->HasTelemetry(); Record.bDemo=Data->bIsDemoData;
                Record.LastUpdate=Data->LastUpdateSeconds; Record.TaskId=Data->TaskId; Record.Reason=Data->Reason; Record.DriverId=Data->DriverId;
                if (!Data->Area.IsEmpty()) Record.LocationText=Data->Area;
                if (Record.bAvailable) Record.Value=FString::Printf(TEXT("%.1f t · %.1f km/h"),Data->LoadTonnes,Data->SpeedKmh);
            }
        }
        else if (Record.Type==TEXT("stacker"))
        {
            Record.Metric=TEXT("电量 / 举升"); Record.LocationText=TEXT("地堆作业区");
            if (const auto* Data=Cast<UGHSStackerDataComponent>(Record.Telemetry.Get()); Data && Data->StackerId==Record.Id)
            {
                Record.Status=EnumState(uint8(Data->Status)); Record.bAvailable=Data->HasTelemetry(); Record.bDemo=Data->bIsDemoData;
                Record.LastUpdate=Data->LastUpdateSeconds; Record.TaskId=Data->TaskId;
                if (Record.bAvailable)
                {
                    Record.Progress=Data->BatteryPercent/100.;
                    Record.Value=FString::Printf(TEXT("%.0f%% · %.2f m"),Data->BatteryPercent,Data->ForkHeightCm/100.);
                }
            }
        }
        else if (Record.Type==TEXT("agv"))
        {
            Record.Metric=TEXT("电量"); Record.LocationText=TEXT("AGV 场景位置");
            FString Placement;
            if (SingleTag(Actor->Tags,TEXT("PlacementAssumption="),Placement) && Placement.Contains(TEXT("Charging bay")))
                Record.LocationText=TEXT("充电区");
        }
        else if (Record.Type==TEXT("charger"))
        {
            Record.Metric=TEXT("充电功率"); Record.LocationText=TEXT("充电区");
        }
        Record.bLive=!Record.bDemo && Record.Status!=TEXT("unknown");
        Record.bAlert=Record.Status==TEXT("warning") || Record.Status==TEXT("fault");
    }

    TSharedRef<FJsonObject> Json(const FRecord& Record) const
    {
        FTransform Transform=Record.Transform;
        CurrentTransform(Record,Transform);
        const bool Hidden=!Record.Actor.IsValid() || Record.Actor->IsHidden();
        if(Record.CachedJson.IsValid() && Record.JsonTransform.Equals(Transform,.0001) && Record.bJsonHidden==Hidden)
            return Record.CachedJson.ToSharedRef();
        const auto Result=MakeShared<FJsonObject>();
        Result->SetStringField(TEXT("id"),Record.Id);
        Result->SetStringField(TEXT("kind"),Record.Kind);
        Result->SetStringField(TEXT("type"),Record.Type);
        Result->SetStringField(TEXT("title"),Record.Title);
        Result->SetStringField(TEXT("status"),Record.Status);
        Result->SetStringField(TEXT("location"),Record.LocationText);
        Result->SetStringField(TEXT("metric"),Record.Metric);
        Result->SetStringField(TEXT("value"),Record.Value);
        Result->SetStringField(TEXT("taskId"),Record.TaskId);
        Result->SetStringField(TEXT("dockId"),Record.DockId);
        Result->SetStringField(TEXT("reason"),Record.Reason);
        Result->SetStringField(TEXT("driverId"),Record.DriverId);
        Result->SetBoolField(TEXT("live"),Record.bLive);
        Result->SetBoolField(TEXT("demo"),Record.bDemo);
        Result->SetBoolField(TEXT("available"),Record.bAvailable);
        Result->SetBoolField(TEXT("alert"),Record.bAlert);
        Result->SetBoolField(TEXT("visible"),Record.Actor.IsValid() && !Record.Actor->IsHidden());
        Result->SetNumberField(TEXT("progress"),Record.Progress);
        Result->SetNumberField(TEXT("lastUpdateSeconds"),Record.LastUpdate);
        Result->SetStringField(TEXT("source"),Record.bDemo?TEXT("demo"):(Record.bLive?TEXT("telemetry"):(Record.Kind==TEXT("device")?TEXT("unknown"):TEXT("scene"))));
        // A cached catalogue must not keep a CAD binding after an unannounced instance move.
        Result->SetStringField(TEXT("cadId"),Transform.GetLocation().Equals(Record.Transform.GetLocation(),.1)?Record.CadId:FString());
        Result->SetNumberField(TEXT("instanceIndex"),Record.InstanceIndex);
        Result->SetStringField(TEXT("mesh"),Record.MeshName);
        if (Record.Level>0) Result->SetNumberField(TEXT("level"),Record.Level);
        if (Record.Column>0) Result->SetNumberField(TEXT("column"),Record.Column);
        if (!Record.ParentId.IsEmpty()) Result->SetStringField(TEXT("rackId"),Record.ParentId);
        if (Record.Kind!=TEXT("device"))
        {
            Result->SetBoolField(TEXT("businessBound"),false);
            Result->SetStringField(TEXT("businessNote"),TEXT("已定位实际场景实例；尚未绑定 SKU、批次和业务库存。"));
        }
        Result->SetStringField(TEXT("component"),Record.Component.IsValid()?Record.Component->GetName():FString());
        Result->SetStringField(TEXT("actor"),Record.Actor.IsValid()?Record.Actor->GetName():FString());
        const FBox Bounds=Record.LocalBounds.TransformBy(Transform);
        SetVector(Result,TEXT("worldPosition"),Bounds.GetCenter());
        SetVector(Result,TEXT("extent"),Bounds.GetExtent());
        Record.CachedJson=Result; Record.JsonTransform=Transform; Record.bJsonHidden=Hidden;
        return Result;
    }
};

FGHSTwinSceneData::FGHSTwinSceneData() : Impl(MakeUnique<FImpl>()) {}
FGHSTwinSceneData::~FGHSTwinSceneData() { Impl->Detach(); Impl->RestoreVisibility(); }

void FGHSTwinSceneData::Refresh(UWorld* World,bool bBootstrapLegacyComponents)
{
    if(Impl->World.Get()!=World)
    {
        Impl->Detach(); Impl->RestoreVisibility();
        Impl=MakeUnique<FImpl>(); Impl->World=World;
        if(IsValid(World)) Impl->Attach(World);
    }
    if(!IsValid(World)) return;
    const FString MapName=World->GetMapName();
    bool bContentChanged=Impl->MapName!=MapName;
    if(bContentChanged) { Impl->MapName=MapName; Impl->bSnapshotDirty=true; }
    Impl->LoadMetadata();
    if(Impl->bWorldRescan || FPlatformTime::Seconds()>=Impl->NextWorldValidation) Impl->Discover();
    bool bRegistryChanged=Impl->bBootstrapNeeded;
    TArray<AActor*> Actors;
    for(auto It=Impl->RegisteredActors.CreateIterator();It;++It)
    {
        AActor* Actor=It.Key().Get();
        if(!Actor || Actor->IsActorBeingDestroyed() || Actor->GetWorld()!=World)
        { It.RemoveCurrent(); bRegistryChanged=true; continue; }
        Actors.Add(Actor); bRegistryChanged|=Impl->InspectActor(Actor,It.Value());
    }
    if(bBootstrapLegacyComponents && (!Impl->bLegacyBootstrapped || Impl->bBootstrapNeeded || bRegistryChanged))
    {
        BootstrapActors(World,Actors);
        Impl->bLegacyBootstrapped=true;
        for(auto& Entry:Impl->RegisteredActors)
            if(auto* Actor=Entry.Key.Get()) bRegistryChanged|=Impl->InspectActor(Actor,Entry.Value);
    }
    Impl->bBootstrapNeeded=false;
    if(bRegistryChanged)
    {
        TMap<FString,int32> Counts;
        for(const auto& Entry:Impl->RegisteredActors)
            if(!Entry.Value.Identity.Id.IsEmpty()) ++Counts.FindOrAdd(Entry.Value.Identity.Id);
        TArray<FImpl::FRecord> Devices;
        for(const auto& Entry:Impl->RegisteredActors)
        {
            AActor* Actor=Entry.Key.Get(); const auto& R=Entry.Value;
            auto* Component=R.DeviceComponent.Get(); auto* Mesh=R.DeviceMesh.Get();
            if(!Actor || !Component || !Component->IsRegistered() || !Mesh || R.Identity.Id.IsEmpty() || Counts.FindRef(R.Identity.Id)!=1) continue;
            FImpl::FRecord Record;
            if(const int32* Old=Impl->DeviceById.Find(R.Identity.Id); Old && Impl->Devices.IsValidIndex(*Old))
            {
                const auto& Prior=Impl->Devices[*Old];
                if(Prior.Actor.Get()==Actor && Prior.Component.Get()==Component && Prior.MeshName==Mesh->GetName()
                    && Prior.DockId==R.Identity.DockId && Prior.LocalBounds.Equals(Mesh->GetBoundingBox()))
                    Record=MoveTemp(Impl->Devices[*Old]);
            }
            Record.Id=R.Identity.Id; Record.Type=R.Identity.Type; Record.Title=R.Identity.Title; Record.DockId=R.Identity.DockId;
            Record.Kind=TEXT("device"); Record.Actor=Actor; Record.Component=Component; Record.Telemetry=R.Telemetry;
            Record.MeshName=Mesh->GetName(); Record.LocalBounds=Mesh->GetBoundingBox();
            Devices.Add(MoveTemp(Record)); Impl->TrackVisibility(Actor,true);
        }
        Impl->Devices=MoveTemp(Devices);
        Impl->Devices.Sort([](const FImpl::FRecord& A,const FImpl::FRecord& B){return A.Id<B.Id;});
        Impl->DeviceById.Reset();
        for(int32 I=0;I<Impl->Devices.Num();++I) Impl->DeviceById.Add(Impl->Devices[I].Id,I);
        Impl->bSnapshotDirty=true;
        bContentChanged=true;
    }
    for(auto& Record:Impl->Devices)
    {
        const FImpl::FRecord Before=Record;
        Record.Status=TEXT("unknown"); Record.LocationText.Empty(); Record.Metric.Empty(); Record.Value=TEXT("—");
        Record.TaskId.Empty(); Record.Reason.Empty(); Record.DriverId.Empty(); Record.Progress=0; Record.LastUpdate=-1;
        Record.bLive=Record.bDemo=Record.bAvailable=Record.bAlert=false;
        FImpl::CurrentTransform(Record,Record.Transform);
        if(!Before.Transform.Equals(Record.Transform,.0001)) bContentChanged=true;
        FImpl::UpdateBounds(Record); Impl->ReadTelemetry(Record);
        if(Before.Status!=Record.Status || Before.LocationText!=Record.LocationText || Before.Metric!=Record.Metric
            || Before.Value!=Record.Value || Before.TaskId!=Record.TaskId || Before.Reason!=Record.Reason || Before.DriverId!=Record.DriverId
            || Before.Progress!=Record.Progress || Before.LastUpdate!=Record.LastUpdate || Before.bLive!=Record.bLive
            || Before.bDemo!=Record.bDemo || Before.bAvailable!=Record.bAvailable || Before.bAlert!=Record.bAlert)
        { Record.CachedJson.Reset(); Impl->bSnapshotDirty=true; bContentChanged=true; }
    }
    TSet<TWeakObjectPtr<UInstancedStaticMeshComponent>> SeenStorage;
    bool bStorageChanged=false;
    for(const auto& Entry:Impl->RegisteredActors)
    {
        if(Entry.Value.bFx) Impl->TrackVisibility(Entry.Key.Get(),true);
        for(const auto& Weak:Entry.Value.Storage)
        {
            auto* Component=Weak.Get(); UStaticMesh* Mesh=Component?Component->GetStaticMesh():nullptr;
            if(!Mesh || !Component->IsRegistered()) continue;
            const FString Name=Mesh->GetName();
            if(!Name.StartsWith(TEXT("SM_GHS_V2Rack_")) && !Name.StartsWith(TEXT("SM_GHS_Presentation_Cargo")) && Name!=TEXT("SM_GHS_V2DockDoor")) continue;
            SeenStorage.Add(Component);
            const bool bNew=!Impl->StorageCaches.Contains(Component);
            auto& Cache=Impl->StorageCaches.FindOrAdd(Component);
            if(bNew) Impl->StorageOrder.Add(Component);
            if(bNew || Cache.Mesh.Get()!=Mesh || Cache.Count!=Component->GetInstanceCount() || !Cache.LocalBounds.Equals(Mesh->GetBoundingBox()))
            { Impl->RebuildStorage(Component,Cache); bStorageChanged=true; }
        }
    }
    for(auto It=Impl->StorageCaches.CreateIterator();It;++It)
        if(!SeenStorage.Contains(It.Key()))
        {
            for(const FString& Id:It.Value().Ids) if(!Id.IsEmpty()) Impl->Records.Remove(Id);
            Impl->StorageOrder.Remove(It.Key()); It.RemoveCurrent();
            bStorageChanged=true; Impl->bSnapshotDirty=true;
        }
    if(bStorageChanged) { Impl->UpdateRegions(); bContentChanged=true; }
    for(auto It=Impl->MaterialSelections.CreateIterator();It;++It)
    {
        auto& Selection=It.Value(); const auto* Rack=Impl->Find(Selection.ParentId);
        if(!Rack) { It.RemoveCurrent(); continue; }
        if(Selection.CadId!=Rack->CadId || !Selection.Transform.Equals(Rack->Transform,.0001))
        { Selection.CadId=Rack->CadId; Selection.Transform=Rack->Transform; Selection.CachedJson.Reset(); }
        Selection.Actor=Rack->Actor; Selection.Component=Rack->Component;
    }
    Impl->Visibility.RemoveAll([this](const FImpl::FVisibility& Item)
    { if(Item.Actor.IsValid()) return false; Impl->VisibilityTracked.Remove(Item.Actor); return true; });
    Impl->UpdateLayers();
    Impl->Stats.RegisteredActors=Impl->RegisteredActors.Num(); Impl->Stats.StorageComponents=Impl->StorageCaches.Num();
    if(bContentChanged) ++Impl->Revision;
}

void FGHSTwinSceneData::MaintainCache(int32 InstanceBudget)
{
    if(InstanceBudget<=0 || !Impl->World.IsValid() || Impl->StorageOrder.IsEmpty()) return;
    // Index events flag catalogue changes; transforms need bounded real-data verification:
    // UpdateInstanceTransform(..., bMarkRenderStateDirty=false) emits no public change delegate.
    // Never reset a partially verified cursor on render dirtiness: continuous edits must not
    // starve later instances or force a full component rebuild into one frame.
    int32 Remaining=InstanceBudget, EmptyVisits=0;
    bool bChanged=false;
    while(Remaining>0 && EmptyVisits<Impl->StorageOrder.Num())
    {
        Impl->StorageCursor%=Impl->StorageOrder.Num();
        const auto Weak=Impl->StorageOrder[Impl->StorageCursor];
        auto* Component=Weak.Get(); auto* Cache=Impl->StorageCaches.Find(Weak);
        if(!Component || !Cache || !Cache->Mesh.IsValid() || !Component->IsRegistered()
            || Cache->Mesh.Get()!=Component->GetStaticMesh() || Cache->Count!=Component->GetInstanceCount() || Cache->Count==0)
        { ++Impl->StorageCursor; ++EmptyVisits; continue; }
        const int32 Count=FMath::Min(Remaining,Cache->Count-Cache->Cursor);
        for(int32 I=0;I<Count;++I)
        {
            const int32 Index=Cache->Cursor++; FTransform Transform; ++Impl->Stats.InstancesVerified;
            if(Component->GetInstanceTransform(Index,Transform,true) && !Cache->Transforms[Index].Equals(Transform,.0001))
            { Impl->UpdateInstance(Component,*Cache,Index,Transform); bChanged=true; }
        }
        Remaining-=Count;
        if(Cache->Cursor>=Cache->Count)
        { Cache->Cursor=0; ++Impl->StorageCursor; ++EmptyVisits; }
    }
    if(bChanged) { Impl->UpdateRegions(); ++Impl->Revision; }
}

FGHSTwinSceneCacheStats FGHSTwinSceneData::GetCacheStats() const { return Impl->Stats; }
uint64 FGHSTwinSceneData::GetRevision() const { return Impl->Revision; }
FString FGHSTwinSceneData::SnapshotJson(const FString& SelectedId) const
{
    // Cheap transform/visibility comparison, without allocating JSON or computing bounds.
    for(const auto& Record:Impl->Devices)
    {
        FTransform Transform;
        if(!Record.Actor.IsValid() || Record.Actor->IsActorBeingDestroyed() || !FImpl::CurrentTransform(Record,Transform))
        { Impl->bSnapshotDirty=true; continue; }
        if(!Record.CachedJson.IsValid() || !Record.JsonTransform.Equals(Transform,.0001) || Record.bJsonHidden!=Record.Actor->IsHidden())
            Impl->bSnapshotDirty=true;
    }
    if(Impl->bSnapshotDirty || Impl->CachedSnapshotBase.IsEmpty())
    {
        const auto Root=MakeShared<FJsonObject>();
        Root->SetBoolField(TEXT("connected"),Impl->World.IsValid()); Root->SetStringField(TEXT("mapName"),Impl->MapName);
        TArray<TSharedPtr<FJsonValue>> Equipment,Facilities;
        for(const auto& Record:Impl->Devices)
            if(Impl->Find(Record.Id))
                (Record.Type==TEXT("charger")?Facilities:Equipment).Add(MakeShared<FJsonValueObject>(Impl->Json(Record)));
        Root->SetArrayField(TEXT("equipment"),Equipment); Root->SetArrayField(TEXT("facilities"),Facilities);
        Root->SetNumberField(TEXT("rackInstanceCount"),Impl->RackInstanceCount);
        Impl->CachedSnapshotBase.Empty();
        FJsonSerializer::Serialize(Root,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Impl->CachedSnapshotBase));
        ++Impl->Stats.SnapshotSerializations; Impl->bSnapshotDirty=false;
    }
    if(SelectedId.IsEmpty()) return Impl->CachedSnapshotBase;
    FString Selection=TEXT("null");
    if(const auto* Selected=Impl->Find(SelectedId))
    {
        const auto Object=Impl->Json(*Selected);
        if(Impl->CachedSelectionObject!=Object)
        {
            Impl->CachedSelectionJson.Empty();
            FJsonSerializer::Serialize(Object,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Impl->CachedSelectionJson));
            Impl->CachedSelectionObject=Object; ++Impl->Stats.SnapshotSerializations;
        }
        Selection=Impl->CachedSelectionJson;
    }
    return Impl->CachedSnapshotBase.LeftChop(1)+TEXT(",\"selection\":")+Selection+TEXT("}");
}

bool FGHSTwinSceneData::BuildSnapshotIfChanged(const FString& SelectedId,FString& OutJson,bool bForce)
{
    FString Current=SnapshotJson(SelectedId);
    if(!bForce && Impl->bHasSentSnapshot && Current==Impl->LastSentSnapshot) { OutJson.Empty(); return false; }
    Impl->LastSentSnapshot=Current; Impl->bHasSentSnapshot=true; OutJson=MoveTemp(Current); return true;
}
bool FGHSTwinSceneData::Resolve(const FString& Id,FVector& OutLocation,FVector& OutExtent) const
{
    const auto* Record=Impl->Find(Id);
    if (!Record && Id.StartsWith(TEXT("DOCK-")))
        Record=Impl->Devices.FindByPredicate([&Id](const FImpl::FRecord& Candidate) { return Candidate.DockId==Id && Candidate.Actor.IsValid(); });
    if (!Record) return false;
    FTransform Transform;
    if (!FImpl::CurrentTransform(*Record,Transform)) return false;
    const FBox Bounds=Record->LocalBounds.TransformBy(Transform);
    OutLocation=Bounds.GetCenter(); OutExtent=Bounds.GetExtent();
    return true;
}

bool FGHSTwinSceneData::ResolvePoint(const FString& Id,FVector& OutLocation) const
{
    FVector Center,Extent;
    const bool bResolved=Id.StartsWith(TEXT("REGION:"))
        ?RegionBounds(Id.Mid(7),Center,Extent):Resolve(Id,Center,Extent);
    if(!bResolved) return false;
    OutLocation=Center+FVector(0,0,Extent.Z+80); return true;
}

bool FGHSTwinSceneData::RegionBounds(const FString& Region,FVector& OutLocation,FVector& OutExtent) const
{
    if (!Impl->World.IsValid()) return false;
    const FBox* Bounds=Region==TEXT("racks")?&Impl->RackRegion:Region==TEXT("floor")?&Impl->FloorRegion:nullptr;
    if (!Bounds || !Bounds->IsValid) return false;
    OutLocation=Bounds->GetCenter(); OutExtent=Bounds->GetExtent(); return true;
}

bool FGHSTwinSceneData::Pick(APlayerController* Controller,const FVector2D& ScreenPosition,FString& OutId)
{
    OutId.Empty();
    if (!IsValid(Controller) || ScreenPosition.ContainsNaN() || Controller->GetWorld()!=Impl->World.Get()) return false;
    FVector Origin,Direction;
    if (!Controller->DeprojectScreenPositionToWorld(ScreenPosition.X,ScreenPosition.Y,Origin,Direction)) return false;
    return PickRay(Origin,Direction,OutId);
}

bool FGHSTwinSceneData::PickRay(const FVector& Origin,const FVector& Direction,FString& OutId)
{
    OutId.Empty();
    double Closest=TNumericLimits<double>::Max();
    const FImpl::FRecord* Selected=nullptr;
    const FImpl::FSlot* SelectedSlot=nullptr;
    auto Consider=[&](const FImpl::FRecord& Record)
    {
        if (!Record.Actor.IsValid() || Record.Actor->IsActorBeingDestroyed() || Record.Actor->IsHidden() || !Record.Component.IsValid()
            || !Record.Component->IsVisible() || Record.Component->bHiddenInGame) return;
        if (Record.Kind==TEXT("dock")) return;
        FTransform Transform;
        if (!FImpl::CurrentTransform(Record,Transform)) return;
        double Distance=0;
        if (!GHSTwinSelection::IntersectBox(Origin,Direction,Transform,Record.LocalBounds,Distance)) return;
        const FImpl::FSlot* HitSlot=nullptr;
        if (Record.Kind==TEXT("rack"))
        {
            const auto* Slots=Impl->SlotsByMesh.Find(Record.MeshName);
            double SlotDistance=TNumericLimits<double>::Max();
            if (Slots) for (const auto& Slot : *Slots)
            {
                double Hit=0;
                if (GHSTwinSelection::IntersectBox(Origin,Direction,Transform,Slot.Bounds,Hit) && Hit<SlotDistance)
                { SlotDistance=Hit; HitSlot=&Slot; }
            }
            if (HitSlot) Distance=SlotDistance;
            else return; // Rack steel is context; only its actual cargo slots can be selected.
        }
        if (Distance<Closest)
        { Closest=Distance; Selected=&Record; SelectedSlot=HitSlot; }
    };
    for(const auto& Record:Impl->Devices) Consider(Record);
    for(const auto& Entry:Impl->Records) Consider(Entry.Value);
    if (!Selected) return false;
    OutId=Selected->Id;
    if (SelectedSlot)
    {
        FImpl::FRecord Material=*Selected;
        Material.ParentId=Selected->Id;
        Material.Id=FString::Printf(TEXT("MATERIAL:%s:L%d:C%d"),*Selected->Id,SelectedSlot->Level,SelectedSlot->Column);
        Material.Kind=TEXT("material"); Material.Type=TEXT("pallet");
        Material.Title=FString::Printf(TEXT("货架托盘 · 第 %d 层 / 第 %d 列"),SelectedSlot->Level,SelectedSlot->Column);
        Material.Level=SelectedSlot->Level; Material.Column=SelectedSlot->Column; Material.LocalBounds=SelectedSlot->Bounds;
        Material.CachedJson.Reset();
        FImpl::CurrentTransform(Material,Material.Transform);
        if(!Material.Transform.GetLocation().Equals(Selected->Transform.GetLocation(),.1)) Material.CadId.Empty();
        FImpl::UpdateBounds(Material); OutId=Material.Id;
        if (Impl->MaterialSelections.Num()>=64 && !Impl->MaterialSelections.Contains(OutId)) Impl->MaterialSelections.Reset();
        Impl->MaterialSelections.Add(OutId,MoveTemp(Material));
    }
    return true;
}

TArray<FGHSTwinPoint> FGHSTwinSceneData::Points() const
{
    TArray<FGHSTwinPoint> Result;
    Result.Reserve(Impl->Devices.Num()+2);
    for (const auto& Record:Impl->Devices)
        if(Record.Actor.IsValid() && !Record.Actor->IsActorBeingDestroyed() && !Record.Actor->IsHidden())
        {
            FVector Location;
            if(ResolvePoint(Record.Id,Location))
            {
                Result.Add({Record.Id,Record.Id,Record.Type,Record.Status,Location,Record.bAlert});
            }
        }
    if (Impl->bRacksVisible)
    {
        FVector Center,Extent;
        if (RegionBounds(TEXT("racks"),Center,Extent)) Result.Add({TEXT("REGION:racks"),TEXT("货架区域"),TEXT("rack"),TEXT("scene"),Center+FVector(0,0,Extent.Z+80),false});
        if (RegionBounds(TEXT("floor"),Center,Extent)) Result.Add({TEXT("REGION:floor"),TEXT("地堆区域"),TEXT("pallet"),TEXT("scene"),Center+FVector(0,0,Extent.Z+80),false});
    }
    return Result;
}

void FGHSTwinSceneData::ApplyLayers(bool Equipment,bool Racks)
{
    if(Impl->bEquipmentVisible!=Equipment || Impl->bRacksVisible!=Racks)
    { ++Impl->Revision; Impl->bSnapshotDirty=true; }
    Impl->bEquipmentVisible=Equipment; Impl->bRacksVisible=Racks; Impl->UpdateLayers();
}
