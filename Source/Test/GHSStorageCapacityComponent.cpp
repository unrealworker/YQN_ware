#include "GHSStorageCapacityComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include <numeric>

namespace GHSStorageCapacity
{
int32 SlotRank(int32 GlobalSlot,int32 TotalSlots)
{
    if (TotalSlots<=0 || GlobalSlot<0 || GlobalSlot>=TotalSlots) return INDEX_NONE;
    int32 Multiplier=97;
    if (TotalSlots%97==0)
    {
        Multiplier=101;
        while (std::gcd(Multiplier,TotalSlots)!=1) Multiplier+=2;
    }
    return int32((int64(GlobalSlot)*Multiplier+17)%TotalSlots);
}
bool IsSlotVisible(int32 GlobalSlot,int32 TotalSlots,float Capacity)
{
    const int32 Rank=SlotRank(GlobalSlot,TotalSlots);
    return Rank>=0 && FMath::IsFinite(Capacity)
        && Rank<FMath::FloorToInt(FMath::Clamp(Capacity,0.f,1.f)*TotalSlots+.5f);
}
float ClampCapacity(float Value,float Previous)
{
    return FMath::IsFinite(Value)?FMath::Clamp(Value,0.f,1.f):Previous;
}
}

UGHSStorageCapacityComponent::UGHSStorageCapacityComponent()
{
    PrimaryComponentTick.bCanEverTick=false;
}

void UGHSStorageCapacityComponent::BeginPlay()
{
    Super::BeginPlay();
    if(!bDeferWorldInitialization)InitializeForWorld();
}

bool UGHSStorageCapacityComponent::InitializeForWorld()
{
    if(bInitialized) return true;
    if(!GetWorld()) return false;
    FString Text;
    TSharedPtr<FJsonObject> Root;
    if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data/storage-capacity.json")))
        || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root.IsValid())
    { InitializationError=TEXT("Missing or invalid storage-capacity.json"); return false; }
    const TArray<TSharedPtr<FJsonValue>>* Definitions=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Meshes=nullptr;
    double RackCount=0,FloorCount=0;
    if(!Root->TryGetNumberField(TEXT("rack_total_slots"),RackCount)
        || !Root->TryGetNumberField(TEXT("floor_total_slots"),FloorCount)
        || !Root->TryGetArrayField(TEXT("groups"),Definitions)
        || !Root->TryGetArrayField(TEXT("meshes"),Meshes))
    { InitializationError=TEXT("Storage metadata is incomplete"); return false; }
    RackTotalSlots=int32(RackCount); FloorTotalSlots=int32(FloorCount);
    const auto Inventory=FGHSLocationInventory::Shared();
    TMap<FString,TSharedPtr<FJsonObject>> CadGroups;
    TMap<FString,FString> InventoryMaterials;
    FString ExtraText;TSharedPtr<FJsonObject> Extra;
    const FString DataRoot=FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data");
    if(FFileHelper::LoadFileToString(ExtraText,*(DataRoot/TEXT("scene-bindings.json")))
        && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ExtraText),Extra) && Extra)
    {
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(Extra->TryGetArrayField(TEXT("groups"),Rows)) for(const auto& Value:*Rows)
        {
            const auto Row=Value->AsObject();FString Mesh;
            if(Row && Row->TryGetStringField(TEXT("mesh"),Mesh)) CadGroups.Add(Mesh,Row);
        }
    }
    Extra.Reset();ExtraText.Empty();
    if(FFileHelper::LoadFileToString(ExtraText,*(DataRoot/TEXT("inventory-materials.json")))
        && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ExtraText),Extra) && Extra)
    {
        const TSharedPtr<FJsonObject>* Materials=nullptr;double Version=0;
        if(Extra->TryGetNumberField(TEXT("schemaVersion"),Version) && Version==1 && Extra->TryGetObjectField(TEXT("materials"),Materials))
            for(const auto& Entry:(*Materials)->Values) {FString Path;if(Entry.Value->TryGetString(Path)) InventoryMaterials.Add(FString(Entry.Key.ToView()),Path);}
    }
    TMap<FString,TSharedPtr<FJsonObject>> GroupsByTag,MeshesByName;
    for(const auto& Value:*Definitions)
        if(const auto Definition=Value->AsObject(); Definition.IsValid())
            GroupsByTag.Add(TEXT("GHSStorageGroup:")+Definition->GetStringField(TEXT("actor")),Definition);
    for(const auto& Value:*Meshes)
        if(const auto Definition=Value->AsObject(); Definition.IsValid())
            MeshesByName.Add(Definition->GetStringField(TEXT("name")),Definition);
    TMap<UMaterialInterface*,UMaterialInstanceDynamic*> RackCache,FloorCache;
    ++InitializationScans;
    for(TActorIterator<AActor> Actor(GetWorld());Actor;++Actor)
    {
        TInlineComponentArray<UInstancedStaticMeshComponent*> Components(*Actor);
        for(auto* Component:Components)
        {
            if(!Component->GetStaticMesh()) continue;
            TSharedPtr<FJsonObject> Definition;
            for(const FName& Tag:Component->ComponentTags)
                if(const auto* Found=GroupsByTag.Find(Tag.ToString())) { Definition=*Found; break; }
            if(!Definition.IsValid()) continue;
            const FString MeshName=Component->GetStaticMesh()->GetName();
            const auto* Mesh=MeshesByName.Find(MeshName);
            if(!Mesh || MeshName!=Definition->GetStringField(TEXT("mesh"))
                || Component->GetInstanceCount()!=Definition->GetIntegerField(TEXT("count")))
            { InitializationError=TEXT("A storage component does not match its complete-slot metadata: ")+Component->GetPathName(); continue; }
            FGroup Group;
            Group.Component=Component;
            Group.bRack=Definition->GetStringField(TEXT("kind"))==TEXT("rack");
            Group.BaseSlot=Definition->GetIntegerField(TEXT("base_slot"));
            Group.SlotsPerInstance=Definition->GetIntegerField(TEXT("slots_per_instance"));
            Group.InstanceCount=Component->GetInstanceCount();
            const TArray<TSharedPtr<FJsonValue>>* Slots=nullptr;
            if((*Mesh)->TryGetArrayField(TEXT("slots"),Slots))
                for(const auto& Value:*Slots)
                {
                    const auto Slot=Value->AsObject();
                    const auto& Low=Slot->GetArrayField(TEXT("min_cm"));
                    const auto& High=Slot->GetArrayField(TEXT("max_cm"));
                    if(Low.Num()!=3 || High.Num()!=3) continue;
                    FSlot Item;
                    Item.Index=Slot->GetIntegerField(TEXT("index"));
                    Item.Level=Slot->GetIntegerField(TEXT("level"));Item.Column=Slot->GetIntegerField(TEXT("column"));
                    Item.Bounds=FBox(FVector(Low[0]->AsNumber(),Low[1]->AsNumber(),Low[2]->AsNumber()),
                        FVector(High[0]->AsNumber(),High[1]->AsNumber(),High[2]->AsNumber()));
                    Group.Slots.Add(Item);
                }
            if(Group.bRack && Group.Slots.Num()!=Group.SlotsPerInstance)
            { InitializationError=TEXT("Incomplete local rack slots: ")+MeshName; continue; }
            bool bMaterialsReady=true;
            for(int32 Slot=Group.bRack?3:0;Slot<Component->GetNumMaterials();++Slot)
            {
                float Existing=0;
                UMaterialInterface* Material=Component->GetMaterial(Slot);
                if(!Material || !Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("StorageCapacity")),Existing))
                    bMaterialsReady=false;
            }
            if(!bMaterialsReady)
            { InitializationError=TEXT("Missing capacity mask material: ")+Component->GetPathName(); continue; }
            // A group gets inventory bits only when every cargo material supports the same contract.
            TMap<int32,UMaterialInterface*> Replacements;
            bool bInventoryMaterialsReady=Inventory->IsReady() && Group.SlotsPerInstance>0 && Group.SlotsPerInstance<=36;
            for(int32 Slot=Group.bRack?3:0;Slot<Component->GetNumMaterials() && bInventoryMaterialsReady;++Slot)
            {
                UMaterialInterface* Source=Component->GetMaterial(Slot);
                const FString* Path=Source?InventoryMaterials.Find(Source->GetPathName()):nullptr;
                UMaterialInterface* Replacement=Path?LoadObject<UMaterialInterface>(nullptr,**Path):nullptr;
                float Marker=0,CapacityValue=0;
                if(!Replacement || !Replacement->GetScalarParameterValue(FMaterialParameterInfo(TEXT("InventoryMaskVersion")),Marker) || Marker!=1.f
                    || !Replacement->GetScalarParameterValue(FMaterialParameterInfo(TEXT("StorageCapacity")),CapacityValue)) bInventoryMaterialsReady=false;
                else Replacements.Add(Slot,Replacement);
            }
            Group.InventoryMasks.SetNum(Group.InstanceCount);
            Group.InventoryCadIds.SetNum(Group.InstanceCount);
            if(bInventoryMaterialsReady)
            {
                FString SourceMesh;Definition->TryGetStringField(TEXT("source_mesh"),SourceMesh);
                const auto* CadGroup=CadGroups.Find(SourceMesh);
                const TArray<TSharedPtr<FJsonValue>>* CadInstances=nullptr;
                if(CadGroup && (*CadGroup)->TryGetArrayField(TEXT("instances"),CadInstances) && CadInstances->Num()==Group.InstanceCount)
                    for(int32 Instance=0;Instance<Group.InstanceCount;++Instance)
                    {
                        const auto Cad=(*CadInstances)[Instance]->AsObject();FString Id;const TArray<TSharedPtr<FJsonValue>>* Position=nullptr;
                        FTransform Actual;
                        if(!Cad || !Cad->TryGetStringField(TEXT("id"),Id) || !Cad->TryGetArrayField(TEXT("position_m"),Position) || Position->Num()!=3
                            || !Component->GetInstanceTransform(Instance,Actual,true)) continue;
                        const FVector Expected((*Position)[0]->AsNumber()*100,-(*Position)[1]->AsNumber()*100,(*Position)[2]->AsNumber()*100);
                        if(!Actual.GetLocation().Equals(Expected,.1) || !Inventory->MatchesTransform(Id,MeshName,Actual)) continue;
                        Group.InventoryCadIds[Instance]=Id;
                        auto Bind=[&](int32 LocalSlot,int32 Level,int32 Column)
                        {
                            const auto* Location=Inventory->Find(Id,Level,Column);
                            if(!Location || Location->State==EGHSInventoryState::Unknown || !Group.InventoryMasks[Instance].Set(LocalSlot,Location->State)) return;
                            ++BoundInventorySlots;
                            if(Location->State==EGHSInventoryState::Empty) ++EmptyInventorySlots;else ++OccupiedInventorySlots;
                        };
                        if(Group.bRack) for(const FSlot& Slot:Group.Slots) Bind(Slot.Index,Slot.Level,Slot.Column);
                        else Bind(0,0,0);
                    }
            }
            // Authored Always compensated for MID-only opacity-mask changes. Keep the
            // same shadows, but only force them live while capacity is being edited.
            Group.bRestoreAlwaysShadowInvalidation=Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always;
            if(Group.bRestoreAlwaysShadowInvalidation)
                Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Auto;
            // Assign once. Slider updates never touch instance data or the HISM tree.
            Group.OriginalCustomDataFloats=Component->NumCustomDataFloats;
            Group.OriginalCustomData=Component->PerInstanceSMCustomData;
            if(Component->NumCustomDataFloats<(bInventoryMaterialsReady?5:1)) Component->SetNumCustomDataFloats(bInventoryMaterialsReady?5:1);
            for(int32 Index=0;Index<Group.InstanceCount;++Index)
            {
                Component->SetCustomDataValue(Index,0,float(Group.BaseSlot+Index*Group.SlotsPerInstance),false);
                if(bInventoryMaterialsReady) for(int32 Word=0;Word<4;++Word)
                    Component->SetCustomDataValue(Index,Word+1,Group.InventoryMasks[Index].Values[Word],false);
            }
            Component->MarkRenderStateDirty();
            auto& Cache=Group.bRack?RackCache:FloorCache;
            auto& Materials=Group.bRack?RackMaterials:FloorMaterials;
            for(int32 Slot=0;Slot<Component->GetNumMaterials();++Slot)
            {
                UMaterialInterface* Original=Component->GetMaterial(Slot);
                UMaterialInterface* Source=bInventoryMaterialsReady && Replacements.Contains(Slot)?Replacements[Slot]:Original;
                float ExistingCapacity=0;
                if(!Source || !Source->GetScalarParameterValue(FMaterialParameterInfo(TEXT("StorageCapacity")),ExistingCapacity)) continue;
                UMaterialInstanceDynamic* Instance=Cache.FindRef(Source);
                if(!Instance)
                {
                    Instance=UMaterialInstanceDynamic::Create(Source,this);
                    Instance->SetScalarParameterValue(TEXT("StorageCapacity"),Group.bRack?RackCapacity:FloorCapacity);
                    ++ParameterWrites;
                    Cache.Add(Source,Instance); Materials.Add(Instance);
                }
                SourceMaterials.Add(Original); SourceMaterialSlots.Emplace(Component,Slot);
                Component->SetMaterial(Slot,Instance);
            }
            GroupByComponent.Add(Component,Groups.Num());
            Groups.Add(MoveTemp(Group));
            Component->SetVisibility(bStorageVisible,false);
        }
    }
    bInitialized=!Groups.IsEmpty();
    if(!bInitialized && InitializationError.IsEmpty()) InitializationError=TEXT("No prepared storage components found in this world");
    return bInitialized;
}

void UGHSStorageCapacityComponent::VerifyInventoryInstance(UInstancedStaticMeshComponent* Component,int32 Instance,const FTransform& Transform)
{
    const int32* GroupIndex=GroupByComponent.Find(Component);
    if(!GroupIndex) return;
    auto& Group=Groups[*GroupIndex];
    if(!Group.InventoryMasks.IsValidIndex(Instance) || Group.InventoryCadIds[Instance].IsEmpty()) return;
    auto& Mask=Group.InventoryMasks[Instance];FGHSInventoryMask Desired;
    const auto Inventory=FGHSLocationInventory::Shared();
    if(Component->GetStaticMesh() && Inventory->MatchesTransform(Group.InventoryCadIds[Instance],Component->GetStaticMesh()->GetName(),Transform))
    {
        auto Bind=[&](int32 Slot,int32 Level,int32 Column)
        {if(const auto* Location=Inventory->Find(Group.InventoryCadIds[Instance],Level,Column)) Desired.Set(Slot,Location->State);};
        if(Group.bRack) for(const FSlot& Slot:Group.Slots) Bind(Slot.Index,Slot.Level,Slot.Column);else Bind(0,0,0);
    }
    bool bChanged=false;
    for(int32 Word=0;Word<4;++Word) bChanged|=Mask.Values[Word]!=Desired.Values[Word];
    if(!bChanged) return;
    for(int32 Slot=0;Slot<Group.SlotsPerInstance;++Slot)
    {
        if(Mask.IsKnown(Slot))
        {--BoundInventorySlots;if((uint32(Mask.Values[Slot/18])&(1u<<(Slot%18)))!=0) --OccupiedInventorySlots;else --EmptyInventorySlots;}
        if(Desired.IsKnown(Slot))
        {++BoundInventorySlots;if((uint32(Desired.Values[Slot/18])&(1u<<(Slot%18)))!=0) ++OccupiedInventorySlots;else ++EmptyInventorySlots;}
    }
    Mask=Desired;
    WriteInstanceMask(Group,Instance);
}

bool UGHSStorageCapacityComponent::WriteInstanceMask(FGroup& Group,int32 Instance)
{
    auto* Component=Group.Component.Get();
    if(!Component || Component->NumCustomDataFloats<5 || Instance<0 || Instance>=Component->GetInstanceCount()) return false;
    FGHSInventoryMask Display=Group.InventoryMasks[Instance];
    const uint64 Hidden=Group.ReplayHiddenSlots.FindRef(Instance);
    for(int32 Slot=0;Slot<Group.SlotsPerInstance && Hidden;++Slot)
        if(Hidden&(uint64(1)<<Slot)) Display.Set(Slot,EGHSInventoryState::Empty);
    bool bWritten=true;
    for(int32 Word=0;Word<4;++Word) bWritten&=Component->SetCustomDataValue(Instance,Word+1,Display.Values[Word],false);
    Component->MarkRenderStateDirty();
    return bWritten;
}

bool UGHSStorageCapacityComponent::ResolveReplaySlot(UInstancedStaticMeshComponent* Component,int32 Instance,const FString& CadId,
    int32 Level,int32 Column,const FString& LocationId,const FString& LocationCode,int32& Slot,FBox& WorldBounds) const
{
    const int32* GroupIndex=GroupByComponent.Find(Component);
    if(!GroupIndex || !Component || !Component->GetStaticMesh() || Component->NumCustomDataFloats<5) return false;
    const auto& Group=Groups[*GroupIndex];
    if(!Group.bRack || !Group.InventoryCadIds.IsValidIndex(Instance) || Group.InventoryCadIds[Instance]!=CadId) return false;
    FTransform Transform;
    if(!Component->GetInstanceTransform(Instance,Transform,true)) return false;
    const auto* Location=FGHSLocationInventory::Shared()->FindForTransform(CadId,Level,Column,Component->GetStaticMesh()->GetName(),Transform);
    if(!Location || Location->State!=EGHSInventoryState::Occupied || Location->Id!=LocationId || Location->Code!=LocationCode) return false;
    const FSlot* Match=Group.Slots.FindByPredicate([&](const FSlot& Item){return Item.Level==Level && Item.Column==Column;});
    if(!Match || !Group.InventoryMasks[Instance].IsKnown(Match->Index)) return false;
    Slot=Match->Index;
    WorldBounds=Match->Bounds.TransformBy(Transform);
    return true;
}

bool UGHSStorageCapacityComponent::SetReplaySlotHidden(UInstancedStaticMeshComponent* Component,int32 Instance,int32 Slot,bool bHidden)
{
    const int32* GroupIndex=GroupByComponent.Find(Component);
    if(!GroupIndex) return false;
    auto& Group=Groups[*GroupIndex];
    if(!Group.bRack || !Group.InventoryMasks.IsValidIndex(Instance) || Slot<0 || Slot>=Group.SlotsPerInstance || Slot>=36) return false;
    const uint64 Bit=uint64(1)<<Slot;
    const uint64 Previous=Group.ReplayHiddenSlots.FindRef(Instance);
    const uint64 Next=bHidden?(Previous|Bit):(Previous&~Bit);
    if(Previous==Next) return true;
    if(Next) Group.ReplayHiddenSlots.Add(Instance,Next);
    else Group.ReplayHiddenSlots.Remove(Instance);
    if(WriteInstanceMask(Group,Instance)) return true;
    if(Previous) Group.ReplayHiddenSlots.Add(Instance,Previous);
    else Group.ReplayHiddenSlots.Remove(Instance);
    WriteInstanceMask(Group,Instance);
    return false;
}

void UGHSStorageCapacityComponent::SetCapacity(float Rack,float Floor)
{
    Rack=GHSStorageCapacity::ClampCapacity(Rack,RackCapacity);
    Floor=GHSStorageCapacity::ClampCapacity(Floor,FloorCapacity);
    const bool bRackChanged=Rack!=RackCapacity, bFloorChanged=Floor!=FloorCapacity;
    if(!bRackChanged && !bFloorChanged) return;
    BeginCapacityShadowUpdate(bRackChanged,bFloorChanged);
    ++CapacityUpdates;
    if(bRackChanged)
    {
        RackCapacity=Rack;
        for(UMaterialInstanceDynamic* Material:RackMaterials)
            if(Material) { Material->SetScalarParameterValue(TEXT("StorageCapacity"),Rack); ++ParameterWrites; }
    }
    if(bFloorChanged)
    {
        FloorCapacity=Floor;
        for(UMaterialInstanceDynamic* Material:FloorMaterials)
            if(Material) { Material->SetScalarParameterValue(TEXT("StorageCapacity"),Floor); ++ParameterWrites; }
    }
}

void UGHSStorageCapacityComponent::BeginCapacityShadowUpdate(bool bRackChanged,bool bFloorChanged)
{
    bool bPending=false;
    for(FGroup& Group:Groups)
    {
        if(Group.bRack?bRackChanged:bFloorChanged)
            if(auto* Component=Group.Component.Get())
            {
                if(Group.bShadowCacheRefreshing && Component->ShadowCacheInvalidationBehavior!=EShadowCacheInvalidationBehavior::Always)
                    Group.bShadowCacheRefreshing=false;
                if(Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Auto)
                {
                    // One proxy refresh on entry, never one per slider input. While
                    // Always is active, every MID change casts the current mask.
                    Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Always;
                    Group.bShadowCacheRefreshing=true;
                    Component->MarkRenderStateDirty();
                    ++ShadowCacheRefreshRequests;
                }
                else if(!Group.bShadowCacheRefreshing)
                {
                    // Preserve a caller's explicit policy; material-only changes still
                    // need invalidation, including Rigid/Static policies.
                    Component->MarkRenderStateDirty();
                    ++ShadowCacheRefreshRequests;
                }
            }
        bPending|=Group.bShadowCacheRefreshing;
    }
    if(bPending && GetWorld())
        GetWorld()->GetTimerManager().SetTimer(ShadowCacheSettleTimer,this,
            &UGHSStorageCapacityComponent::RestoreCachedShadows,.1f,false);
}

void UGHSStorageCapacityComponent::RestoreCachedShadows()
{
    for(FGroup& Group:Groups) if(Group.bShadowCacheRefreshing)
    {
        Group.bShadowCacheRefreshing=false;
        if(auto* Component=Group.Component.Get(); Component &&
            Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always)
        {
            // Recreate with the final mask before caching. Do not overwrite a policy
            // another runtime owner changed while our settle timer was pending.
            Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Auto;
            Component->MarkRenderStateDirty();
            ++ShadowCacheRefreshRequests;
        }
    }
}

void UGHSStorageCapacityComponent::SetStorageVisible(bool bVisible)
{
    if(bStorageVisible==bVisible) return;
    bStorageVisible=bVisible;
    for(const FGroup& Group:Groups)
        if(auto* Component=Group.Component.Get()) Component->SetVisibility(bVisible,false);
}

bool UGHSStorageCapacityComponent::IsStorageHitVisible(UPrimitiveComponent* Component,int32 InstanceIndex,const FVector& WorldPoint) const
{
    const int32* GroupIndex=GroupByComponent.Find(Component);
    if(!GroupIndex) return true;
    if(!bStorageVisible || !Component || !Component->IsVisible() || Component->bHiddenInGame || WorldPoint.ContainsNaN()) return false;
    const FGroup& Group=Groups[*GroupIndex];
    if(InstanceIndex<0 || InstanceIndex>=Group.InstanceCount) return false;
    const int32 GlobalBase=Group.BaseSlot+InstanceIndex*Group.SlotsPerInstance;
    const auto InventoryVisible=[&](int32 Slot,bool Fallback)
    {
        if(Group.ReplayHiddenSlots.FindRef(InstanceIndex)&(uint64(1)<<Slot)) return false;
        if(!Group.InventoryMasks.IsValidIndex(InstanceIndex) || !Group.InventoryMasks[InstanceIndex].IsKnown(Slot)) return Fallback;
        return (uint32(Group.InventoryMasks[InstanceIndex].Values[Slot/18])&(1u<<(Slot%18)))!=0;
    };
    if(!Group.bRack) return InventoryVisible(0,GHSStorageCapacity::IsSlotVisible(GlobalBase,FloorTotalSlots,FloorCapacity));
    FTransform Transform;
    if(!Group.Component.IsValid() || !Group.Component->GetInstanceTransform(InstanceIndex,Transform,true)) return false;
    const FVector Point=Transform.InverseTransformPosition(WorldPoint);
    for(const FSlot& Slot:Group.Slots)
        if(Slot.Bounds.ExpandBy(.02).IsInsideOrOn(Point))
            return InventoryVisible(Slot.Index,GHSStorageCapacity::IsSlotVisible(GlobalBase+Slot.Index,RackTotalSlots,RackCapacity));
    // A point outside every cargo volume belongs to the retained steel/context.
    return true;
}

FString UGHSStorageCapacityComponent::GetReportJson() const
{
    const auto Report=MakeShared<FJsonObject>();
    Report->SetBoolField(TEXT("initialized"),bInitialized);
    Report->SetStringField(TEXT("error"),InitializationError);
    Report->SetBoolField(TEXT("storage_visible"),bStorageVisible);
    Report->SetNumberField(TEXT("rack_capacity"),RackCapacity);
    Report->SetNumberField(TEXT("floor_capacity"),FloorCapacity);
    Report->SetNumberField(TEXT("rack_total_slots"),RackTotalSlots);
    Report->SetNumberField(TEXT("floor_total_slots"),FloorTotalSlots);
    Report->SetNumberField(TEXT("inventory_bound_slots"),BoundInventorySlots);
    Report->SetNumberField(TEXT("inventory_empty_slots"),EmptyInventorySlots);
    Report->SetNumberField(TEXT("inventory_occupied_slots"),OccupiedInventorySlots);
    int32 VisibleRackSlots=0,VisibleFloorGroups=0;
    if(bStorageVisible) for(const FGroup& Group:Groups)
        for(int32 Instance=0;Instance<Group.InstanceCount;++Instance)
            for(int32 Slot=0;Slot<Group.SlotsPerInstance;++Slot)
            {
                const auto& Mask=Group.InventoryMasks[Instance];
                const bool bVisible=Mask.IsKnown(Slot)
                    ? (uint32(Mask.Values[Slot/18])&(1u<<(Slot%18)))!=0
                    : GHSStorageCapacity::IsSlotVisible(Group.BaseSlot+Instance*Group.SlotsPerInstance+Slot,
                        Group.bRack?RackTotalSlots:FloorTotalSlots,Group.bRack?RackCapacity:FloorCapacity);
                if(bVisible && !(Group.ReplayHiddenSlots.FindRef(Instance)&(uint64(1)<<Slot)))
                {if(Group.bRack) ++VisibleRackSlots;else ++VisibleFloorGroups;}
            }
    Report->SetNumberField(TEXT("rack_visible_slots"),VisibleRackSlots);
    Report->SetNumberField(TEXT("floor_visible_groups"),VisibleFloorGroups);
    Report->SetNumberField(TEXT("registered_components"),Groups.Num());
    Report->SetNumberField(TEXT("shared_materials"),RackMaterials.Num()+FloorMaterials.Num());
    Report->SetNumberField(TEXT("initialization_scans"),double(InitializationScans));
    Report->SetNumberField(TEXT("capacity_updates"),double(CapacityUpdates));
    Report->SetNumberField(TEXT("parameter_writes"),double(ParameterWrites));
    int32 AutoShadowGroups=0, RefreshingShadowGroups=0;
    for(const FGroup& Group:Groups) if(auto* Component=Group.Component.Get())
    {
        if(Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Auto) ++AutoShadowGroups;
        if(Group.bShadowCacheRefreshing) ++RefreshingShadowGroups;
    }
    Report->SetNumberField(TEXT("shadow_cache_auto_components"),AutoShadowGroups);
    Report->SetNumberField(TEXT("shadow_cache_refreshing_components"),RefreshingShadowGroups);
    Report->SetNumberField(TEXT("shadow_cache_refresh_requests"),double(ShadowCacheRefreshRequests));
    FString Result;
    FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Result));
    return Result;
}

void UGHSStorageCapacityComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    ResetForWorld();
    Super::EndPlay(EndPlayReason);
}

void UGHSStorageCapacityComponent::ResetForWorld()
{
    if(GetWorld()) GetWorld()->GetTimerManager().ClearTimer(ShadowCacheSettleTimer);
    for(FGroup& Group:Groups) if(auto* Component=Group.Component.Get())
    {
        bool bChanged=false;
        if(Group.bShadowCacheRefreshing && Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Always)
        { Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Auto; bChanged=true; }
        if(Group.bRestoreAlwaysShadowInvalidation && Component->ShadowCacheInvalidationBehavior==EShadowCacheInvalidationBehavior::Auto)
        { Component->ShadowCacheInvalidationBehavior=EShadowCacheInvalidationBehavior::Always; bChanged=true; }
        Group.bShadowCacheRefreshing=false;
        if(Component->GetInstanceCount()==Group.InstanceCount)
        {
            Component->SetNumCustomDataFloats(Group.OriginalCustomDataFloats);
            for(int32 Index=0;Index<Group.InstanceCount;++Index)
                for(int32 Word=0;Word<Group.OriginalCustomDataFloats;++Word)
                {
                    const int32 Offset=Index*Group.OriginalCustomDataFloats+Word;
                    if(Group.OriginalCustomData.IsValidIndex(Offset))
                        Component->SetCustomDataValue(Index,Word,Group.OriginalCustomData[Offset],false);
                }
            bChanged=true;
        }
        if(bChanged) Component->MarkRenderStateDirty();
    }
    for(int32 Index=0;Index<SourceMaterialSlots.Num();++Index)
        if(auto* Component=SourceMaterialSlots[Index].Key.Get()) Component->SetMaterial(SourceMaterialSlots[Index].Value,SourceMaterials[Index]);
    Groups.Empty();GroupByComponent.Empty();RackMaterials.Empty();FloorMaterials.Empty();
    BoundInventorySlots=EmptyInventorySlots=OccupiedInventorySlots=0;
    SourceMaterials.Empty();SourceMaterialSlots.Empty();bInitialized=false;bStorageVisible=true;InitializationError.Empty();
}
