#include "GHSStorageCapacityComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace GHSStorageCapacity
{
int32 SlotRank(int32 GlobalSlot,int32 TotalSlots)
{
    return TotalSlots>0 && GlobalSlot>=0 && GlobalSlot<TotalSlots ? (GlobalSlot*97+17)%TotalSlots : INDEX_NONE;
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
    InitializeForWorld();
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
            // Assign once. Slider updates never touch instance data or the HISM tree.
            if(Component->NumCustomDataFloats<1) Component->SetNumCustomDataFloats(1);
            for(int32 Index=0;Index<Group.InstanceCount;++Index)
                Component->SetCustomDataValue(Index,0,float(Group.BaseSlot+Index*Group.SlotsPerInstance),false);
            Component->MarkRenderStateDirty();
            auto& Cache=Group.bRack?RackCache:FloorCache;
            auto& Materials=Group.bRack?RackMaterials:FloorMaterials;
            for(int32 Slot=0;Slot<Component->GetNumMaterials();++Slot)
            {
                UMaterialInterface* Source=Component->GetMaterial(Slot);
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
                SourceMaterials.Add(Source); SourceMaterialSlots.Emplace(Component,Slot);
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

void UGHSStorageCapacityComponent::SetCapacity(float Rack,float Floor)
{
    Rack=GHSStorageCapacity::ClampCapacity(Rack,RackCapacity);
    Floor=GHSStorageCapacity::ClampCapacity(Floor,FloorCapacity);
    if(Rack==RackCapacity && Floor==FloorCapacity) return;
    ++CapacityUpdates;
    if(Rack!=RackCapacity)
    {
        RackCapacity=Rack;
        for(UMaterialInstanceDynamic* Material:RackMaterials)
            if(Material) { Material->SetScalarParameterValue(TEXT("StorageCapacity"),Rack); ++ParameterWrites; }
    }
    if(Floor!=FloorCapacity)
    {
        FloorCapacity=Floor;
        for(UMaterialInstanceDynamic* Material:FloorMaterials)
            if(Material) { Material->SetScalarParameterValue(TEXT("StorageCapacity"),Floor); ++ParameterWrites; }
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
    if(!Group.bRack) return GHSStorageCapacity::IsSlotVisible(GlobalBase,FloorTotalSlots,FloorCapacity);
    FTransform Transform;
    if(!Group.Component.IsValid() || !Group.Component->GetInstanceTransform(InstanceIndex,Transform,true)) return false;
    const FVector Point=Transform.InverseTransformPosition(WorldPoint);
    for(const FSlot& Slot:Group.Slots)
        if(Slot.Bounds.ExpandBy(.02).IsInsideOrOn(Point))
            return GHSStorageCapacity::IsSlotVisible(GlobalBase+Slot.Index,RackTotalSlots,RackCapacity);
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
    Report->SetNumberField(TEXT("rack_visible_slots"),bStorageVisible?FMath::FloorToInt(RackCapacity*RackTotalSlots+.5f):0);
    Report->SetNumberField(TEXT("floor_visible_groups"),bStorageVisible?FMath::FloorToInt(FloorCapacity*FloorTotalSlots+.5f):0);
    Report->SetNumberField(TEXT("registered_components"),Groups.Num());
    Report->SetNumberField(TEXT("shared_materials"),RackMaterials.Num()+FloorMaterials.Num());
    Report->SetNumberField(TEXT("initialization_scans"),double(InitializationScans));
    Report->SetNumberField(TEXT("capacity_updates"),double(CapacityUpdates));
    Report->SetNumberField(TEXT("parameter_writes"),double(ParameterWrites));
    FString Result;
    FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Result));
    return Result;
}

void UGHSStorageCapacityComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    for(int32 Index=0;Index<SourceMaterialSlots.Num();++Index)
        if(auto* Component=SourceMaterialSlots[Index].Key.Get()) Component->SetMaterial(SourceMaterialSlots[Index].Value,SourceMaterials[Index]);
    Super::EndPlay(EndPlayReason);
}
