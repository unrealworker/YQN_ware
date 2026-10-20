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

int32 GHSTwinSelection::BootstrapComponents(UWorld* World)
{
    if (!IsValid(World) || !World->IsGameWorld()) return 0;
    UGHSMannedForkliftIdentityLibrary::ReconcileWorld(World);
    int32 Created=0;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        AActor* Actor=*It;
        if (!IsValid(Actor) || Actor->IsActorBeingDestroyed()) continue;
        FIdentity Identity;
        if (!Identify(Actor->Tags,Identity)) continue;
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
        FTransform Transform=FTransform::Identity;
        FBox LocalBounds=FBox(ForceInit);
        FVector Center=FVector::ZeroVector, Extent=FVector::ZeroVector;
        int32 InstanceIndex=INDEX_NONE, Level=0, Column=0;
        double Progress=0, LastUpdate=-1;
        bool bLive=false, bDemo=false, bAvailable=false, bAlert=false;
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
        FTransform ComponentTransform=FTransform::Identity;
        int32 Count=0;
        double CheckedAt=0;
        TArray<FRecord> Entries;
    };

    TWeakObjectPtr<UWorld> World;
    FString MapName;
    TArray<FRecord> Records;
    TArray<FRecord> Devices;
    TMap<FString,int32> ById;
    TMap<FString,int32> DeviceById;
    TMap<FString,FRecord> MaterialSelections;
    TMap<FString,TArray<FCadInstance>> CadByMesh;
    TMap<FString,TArray<FSlot>> SlotsByMesh;
    TMap<TWeakObjectPtr<UInstancedStaticMeshComponent>,FStorageCache> StorageCaches;
    TArray<FGHSTwinPoint> CachedPoints;
    TArray<FGHSTwinPoint> StoragePoints;
    TArray<FVisibility> Visibility;
    bool bMetadataLoaded=false, bEquipmentVisible=true, bRacksVisible=true;
    int32 RackInstanceCount=0;
    FBox RackRegion=FBox(ForceInit), FloorRegion=FBox(ForceInit);

    void RestoreVisibility()
    {
        for (const FVisibility& Item : Visibility)
            if (Item.Actor.IsValid()) Item.Actor->SetActorHiddenInGame(Item.bOriginalHidden);
        Visibility.Reset();
    }

    void TrackVisibility(AActor* Actor, bool bEquipment)
    {
        if (!Actor || !World.IsValid() || !World->IsGameWorld()) return;
        if (Visibility.ContainsByPredicate([Actor](const FVisibility& Item) { return Item.Actor.Get()==Actor; })) return;
        Visibility.Add({Actor,Actor->IsHidden(),bEquipment});
    }

    void UpdateLayers()
    {
        if (!World.IsValid() || !World->IsGameWorld()) return;
        for (const FVisibility& Item : Visibility)
            if (Item.Actor.IsValid()) Item.Actor->SetActorHiddenInGame(Item.bOriginalHidden || !(Item.bEquipment?bEquipmentVisible:bRacksVisible));
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
        if (!Record.Component.IsValid()) return false;
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
        if (const int32* Index=DeviceById.Find(Id))
            return Devices.IsValidIndex(*Index) && Devices[*Index].Actor.IsValid()?&Devices[*Index]:nullptr;
        if (const int32* Index=ById.Find(Id))
            return Records.IsValidIndex(*Index) && Records[*Index].Actor.IsValid()?&Records[*Index]:nullptr;
        const FRecord* Material=MaterialSelections.Find(Id);
        return Material && Material->Actor.IsValid()?Material:nullptr;
    }

    void ReadTelemetry(FRecord& Record)
    {
        AActor* Actor=Record.Actor.Get();
        if (!Actor) return;
        if (Record.Type==TEXT("truck"))
        {
            Record.Metric=TEXT("装载托盘"); Record.LocationText=Record.DockId;
            if (const auto* Data=Actor->FindComponentByClass<UGHSDockTruckDataComponent>(); Data && Data->TruckId==Record.Id)
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
            if (const auto* Data=Actor->FindComponentByClass<UGHSMannedForkliftDataComponent>(); Data && Data->ForkliftId==Record.Id)
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
            if (const auto* Data=Actor->FindComponentByClass<UGHSStackerDataComponent>(); Data && Data->StackerId==Record.Id)
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
        Result->SetStringField(TEXT("cadId"),Record.CadId);
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
        FTransform Transform=Record.Transform;
        CurrentTransform(Record,Transform);
        const FBox Bounds=Record.LocalBounds.TransformBy(Transform);
        SetVector(Result,TEXT("worldPosition"),Bounds.GetCenter());
        SetVector(Result,TEXT("extent"),Bounds.GetExtent());
        return Result;
    }
};

FGHSTwinSceneData::FGHSTwinSceneData() : Impl(MakeUnique<FImpl>()) {}
FGHSTwinSceneData::~FGHSTwinSceneData() { Impl->RestoreVisibility(); }

void FGHSTwinSceneData::Refresh(UWorld* World)
{
    if (Impl->World.Get()!=World)
    {
        Impl->RestoreVisibility(); Impl->World=World; Impl->MaterialSelections.Reset(); Impl->StorageCaches.Reset();
        Impl->Records.Reset(); Impl->ById.Reset(); Impl->StoragePoints.Reset(); Impl->RackInstanceCount=0;
        Impl->RackRegion=FBox(ForceInit); Impl->FloorRegion=FBox(ForceInit);
    }
    Impl->MapName=IsValid(World)?World->GetMapName():FString();
    Impl->Devices.Reset(); Impl->DeviceById.Reset(); Impl->CachedPoints.Reset();
    if (!IsValid(World)) return;
    Impl->LoadMetadata();
    const double Now=FPlatformTime::Seconds();
    bool bStorageChanged=false;
    TSet<TWeakObjectPtr<UInstancedStaticMeshComponent>> SeenStorage;
    TMap<FString,int32> IdentityCounts;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        GHSTwinSelection::FIdentity Identity;
        if (GHSTwinSelection::Identify(It->Tags,Identity)) ++IdentityCounts.FindOrAdd(Identity.Id);
    }
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        AActor* Actor=*It;
        if (!IsValid(Actor) || Actor->IsActorBeingDestroyed()) continue;
        GHSTwinSelection::FIdentity Identity;
        if (GHSTwinSelection::Identify(Actor->Tags,Identity))
        {
            // A copied ID is ambiguous. Never silently bind it to whichever Actor iteration returns first.
            if (IdentityCounts.FindRef(Identity.Id)!=1) continue;
            UStaticMeshComponent* Component=Actor->FindComponentByClass<UStaticMeshComponent>();
            if (!Component || !Component->GetStaticMesh() || Cast<UInstancedStaticMeshComponent>(Component)) continue;
            FImpl::FRecord Record;
            Record.Id=Identity.Id; Record.Type=Identity.Type; Record.Title=Identity.Title; Record.DockId=Identity.DockId;
            Record.Kind=TEXT("device"); Record.Actor=Actor; Record.Component=Component;
            Record.MeshName=Component->GetStaticMesh()->GetName(); Record.Transform=Component->GetComponentTransform();
            Record.LocalBounds=Component->GetStaticMesh()->GetBoundingBox();
            FImpl::UpdateBounds(Record); Impl->ReadTelemetry(Record);
            Impl->Devices.Add(MoveTemp(Record)); Impl->TrackVisibility(Actor,true);
            continue;
        }
        TInlineComponentArray<UInstancedStaticMeshComponent*> Components(Actor);
        for (UInstancedStaticMeshComponent* Component : Components)
        {
            UStaticMesh* Mesh=Component->GetStaticMesh();
            if (!Mesh) continue;
            const FString MeshName=Mesh->GetName();
            const bool bRack=MeshName.StartsWith(TEXT("SM_GHS_V2Rack_"));
            const bool bFloor=MeshName.StartsWith(TEXT("SM_GHS_Presentation_Cargo"));
            const bool bDock=MeshName==TEXT("SM_GHS_V2DockDoor");
            if (!bRack && !bFloor && !bDock) continue;
            SeenStorage.Add(Component);
            auto& Cache=Impl->StorageCaches.FindOrAdd(Component);
            const int32 InstanceCount=Component->GetInstanceCount();
            const bool bRefreshCache=Cache.Mesh.Get()!=Mesh || Cache.Count!=InstanceCount
                || !Cache.ComponentTransform.Equals(Component->GetComponentTransform()) || Now-Cache.CheckedAt>30.;
            if (!bRefreshCache)
            {
                if (!bDock) Impl->TrackVisibility(Actor,false);
                continue;
            }
            bStorageChanged=true;
            Cache.Mesh=Mesh; Cache.Count=InstanceCount; Cache.ComponentTransform=Component->GetComponentTransform();
            Cache.CheckedAt=Now; Cache.Entries.Reset(); Cache.Entries.Reserve(InstanceCount);
            const auto* Metadata=Impl->CadByMesh.Find(MeshName);
            const bool bCountMatches=Metadata && Metadata->Num()==InstanceCount;
            for (int32 Index=0; Index<InstanceCount; ++Index)
            {
                FImpl::FRecord Record;
                if (!Component->GetInstanceTransform(Index,Record.Transform,true)) continue;
                Record.Id=FString::Printf(TEXT("%s:%s:%s:%d"),bRack?TEXT("RACK"):TEXT("PALLET"),*Actor->GetName(),*Component->GetName(),Index);
                Record.Kind=bRack?TEXT("rack"):TEXT("material"); Record.Type=bRack?TEXT("rack"):TEXT("pallet");
                Record.Title=bRack?TEXT("实际货架"):TEXT("地堆托盘"); Record.Status=TEXT("scene");
                Record.Actor=Actor; Record.Component=Component; Record.InstanceIndex=Index; Record.MeshName=MeshName;
                Record.LocalBounds=Mesh->GetBoundingBox(); Record.LocationText=bRack?TEXT("货架区"):TEXT("地堆区");
                Record.bAvailable=true; Record.Metric=TEXT("数据绑定"); Record.Value=TEXT("待绑定业务数据");
                // CAD IDs are only supplied after both the count and the actual instance transform agree.
                if (bCountMatches && (*Metadata)[Index].Position.Equals(Record.Transform.GetLocation(),.1))
                {
                    Record.CadId=(*Metadata)[Index].Id;
                    if (bDock) Record.Id=(*Metadata)[Index].DockId;
                }
                if (bDock)
                {
                    if (!Record.Id.StartsWith(TEXT("DOCK-"))) continue;
                    Record.Kind=Record.Type=TEXT("dock"); Record.Title=TEXT("装卸月台"); Record.LocationText=Record.Id;
                }
                FImpl::UpdateBounds(Record); Cache.Entries.Add(MoveTemp(Record));
            }
            if (!bDock) Impl->TrackVisibility(Actor,false);
        }
        FString FXOwner;
        if (SingleTag(Actor->Tags,TEXT("FXOwner="),FXOwner) || Actor->ActorHasTag(TEXT("AGVAnimatedFX")))
            Impl->TrackVisibility(Actor,true);
    }
    for (auto It=Impl->StorageCaches.CreateIterator(); It; ++It)
        if (!SeenStorage.Contains(It.Key())) { It.RemoveCurrent(); bStorageChanged=true; }
    if (bStorageChanged)
    {
        Impl->Records.Reset(); Impl->ById.Reset(); Impl->StoragePoints.Reset(); Impl->RackInstanceCount=0;
        Impl->RackRegion=FBox(ForceInit); Impl->FloorRegion=FBox(ForceInit);
        for (const auto& Cache : Impl->StorageCaches) Impl->Records.Append(Cache.Value.Entries);
        Impl->Records.Sort([](const FImpl::FRecord& A,const FImpl::FRecord& B) { return A.Id<B.Id; });
        for (int32 Index=0; Index<Impl->Records.Num(); ++Index)
        {
            const auto& Record=Impl->Records[Index];
            Impl->ById.Add(Record.Id,Index);
            // One area POI replaces selectable rack-structure instances.
            if (Record.Kind==TEXT("rack")) { ++Impl->RackInstanceCount; Impl->RackRegion+=FBox(Record.Center-Record.Extent,Record.Center+Record.Extent); }
            else if (Record.Type==TEXT("pallet")) Impl->FloorRegion+=FBox(Record.Center-Record.Extent,Record.Center+Record.Extent);
        }
    }
    Impl->Devices.Sort([](const FImpl::FRecord& A,const FImpl::FRecord& B) { return A.Id<B.Id; });
    for (int32 Index=0; Index<Impl->Devices.Num(); ++Index)
    {
        const auto& Record=Impl->Devices[Index];
        Impl->DeviceById.Add(Record.Id,Index);
        Impl->CachedPoints.Add({Record.Id,Record.Id,Record.Type,Record.Status,
            Record.Center+FVector(0,0,Record.Extent.Z+80),Record.bAlert});
    }
    Impl->CachedPoints.Append(Impl->StoragePoints);
    for (auto It=Impl->MaterialSelections.CreateIterator(); It; ++It)
    {
        FImpl::FRecord& Selection=It.Value();
        const auto* Rack=Impl->Find(Selection.ParentId);
        if (!Rack) { It.RemoveCurrent(); continue; }
        Selection.Actor=Rack->Actor; Selection.Component=Rack->Component; Selection.Transform=Rack->Transform;
        Selection.CadId=Rack->CadId; FImpl::UpdateBounds(Selection);
    }
    Impl->Visibility.RemoveAll([](const FImpl::FVisibility& Item) { return !Item.Actor.IsValid(); });
    Impl->UpdateLayers();
}

FString FGHSTwinSceneData::SnapshotJson(const FString& SelectedId) const
{
    const auto Root=MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("connected"),Impl->World.IsValid());
    Root->SetStringField(TEXT("mapName"),Impl->MapName);
    TArray<TSharedPtr<FJsonValue>> Equipment,Facilities;
    for (const auto& Record : Impl->Devices)
    {
        if (Record.Kind!=TEXT("device") || !Record.Actor.IsValid()) continue;
        (Record.Type==TEXT("charger")?Facilities:Equipment).Add(MakeShared<FJsonValueObject>(Impl->Json(Record)));
    }
    Root->SetArrayField(TEXT("equipment"),Equipment); Root->SetArrayField(TEXT("facilities"),Facilities);
    Root->SetNumberField(TEXT("rackInstanceCount"),Impl->RackInstanceCount);
    if (!SelectedId.IsEmpty())
    {
        if (const auto* Selected=Impl->Find(SelectedId)) Root->SetObjectField(TEXT("selection"),Impl->Json(*Selected));
        else Root->SetField(TEXT("selection"),MakeShared<FJsonValueNull>());
    }
    FString Result;
    FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Result));
    return Result;
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
    for (const auto* Collection : {&Impl->Devices,&Impl->Records})
    for (const auto& Record : *Collection)
    {
        if (!Record.Actor.IsValid() || Record.Actor->IsHidden() || !Record.Component.IsValid()
            || !Record.Component->IsVisible() || Record.Component->bHiddenInGame) continue;
        if (Record.Kind==TEXT("dock")) continue;
        FTransform Transform;
        if (!FImpl::CurrentTransform(Record,Transform)) continue;
        double Distance=0;
        if (!GHSTwinSelection::IntersectBox(Origin,Direction,Transform,Record.LocalBounds,Distance)) continue;
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
            else continue; // Rack steel is context; only its actual cargo slots can be selected.
        }
        if (Distance<Closest)
        { Closest=Distance; Selected=&Record; SelectedSlot=HitSlot; }
    }
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
        FImpl::CurrentTransform(Material,Material.Transform);
        FImpl::UpdateBounds(Material); OutId=Material.Id;
        if (Impl->MaterialSelections.Num()>=64 && !Impl->MaterialSelections.Contains(OutId)) Impl->MaterialSelections.Reset();
        Impl->MaterialSelections.Add(OutId,MoveTemp(Material));
    }
    return true;
}

TArray<FGHSTwinPoint> FGHSTwinSceneData::Points() const
{
    TArray<FGHSTwinPoint> Result;
    for (const auto& Point : Impl->CachedPoints)
        if (const auto* Record=Impl->Find(Point.Id); Record && Record->Actor.IsValid() && !Record->Actor->IsHidden())
        {
            FGHSTwinPoint Current=Point;
            FTransform Transform;
            if (FImpl::CurrentTransform(*Record,Transform))
            {
                const FBox Bounds=Record->LocalBounds.TransformBy(Transform);
                Current.Location=Bounds.GetCenter()+FVector(0,0,Bounds.GetExtent().Z+80);
                Result.Add(MoveTemp(Current));
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
    Impl->bEquipmentVisible=Equipment; Impl->bRacksVisible=Racks; Impl->UpdateLayers();
}
