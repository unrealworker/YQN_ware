#include "GHSLocationInventory.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
THIRD_PARTY_INCLUDES_START
#include <openssl/sha.h>
THIRD_PARTY_INCLUDES_END
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
TSharedPtr<FJsonObject> ParseInventory(const FString& Text)
{
    TSharedPtr<FJsonObject> Root;
    return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root)?Root:nullptr;
}
bool VersionOne(const TSharedPtr<FJsonObject>& Root)
{
    double Version=0;return Root && Root->TryGetNumberField(TEXT("schemaVersion"),Version) && Version==1;
}
bool Warehouse108(const TSharedPtr<FJsonObject>& Root)
{
    if(!Root) return false;
    FString Id,Code;double NumericId=0;
    const bool bCorrectId=(Root->TryGetStringField(TEXT("warehouseId"),Id) && Id==TEXT("108"))
        || (Root->TryGetNumberField(TEXT("warehouseId"),NumericId) && NumericId==108.);
    return bCorrectId && Root->TryGetStringField(TEXT("warehouseCode"),Code) && Code==TEXT("GHS_CA_US");
}
bool SafeShard(const FString& Name)
{
    if(Name.Len()!=8 || !Name.EndsWith(TEXT(".json"),ESearchCase::CaseSensitive)) return false;
    for(int32 I=0;I<3;++I) if(Name[I]<TEXT('0') || Name[I]>TEXT('9')) return false;
    return FCString::Atoi(*Name.Left(3))<128;
}
bool CountField(const TSharedPtr<FJsonObject>& Object,const TCHAR* Name,int32& Out)
{
    double Number=0;
    if(!Object || !Object->TryGetNumberField(Name,Number) || !FMath::IsFinite(Number) || Number<0 || Number>MAX_int32 || FMath::FloorToDouble(Number)!=Number) return false;
    Out=int32(Number);return true;
}
bool VectorField(const TSharedPtr<FJsonObject>& Object,const TCHAR* Name,FVector& Out)
{
    const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;
    double X=0,Y=0,Z=0;
    if(!Object->TryGetArrayField(Name,Values) || Values->Num()!=3
        || !(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y) || !(*Values)[2]->TryGetNumber(Z)) return false;
    Out=FVector(X,Y,Z);return !Out.ContainsNaN();
}
bool SourcesMatch(const TSharedPtr<FJsonObject>& Mapping,const FString& Directory)
{
    const TSharedPtr<FJsonObject>* Hashes=nullptr;
    if(!Mapping->TryGetObjectField(TEXT("sourceHashes"),Hashes)) return false;
    for(const TCHAR* File:{TEXT("scene-bindings.json"),TEXT("rack-slots.json"),TEXT("storage-capacity.json")})
    {
        FString Expected;TArray<uint8> Bytes;uint8 Signature[SHA256_DIGEST_LENGTH];
        if(!(*Hashes)->TryGetStringField(FString(TEXT("Content/GHSTwinUI/data/"))+File,Expected)
            || !FFileHelper::LoadFileToArray(Bytes,*(Directory/TEXT("..")/File))
            || !SHA256(Bytes.GetData(),Bytes.Num(),Signature)
            || !BytesToHex(Signature,SHA256_DIGEST_LENGTH).Equals(Expected,ESearchCase::IgnoreCase)) return false;
    }
    return true;
}
EGHSInventoryState InventoryState(const FString& Name,bool bQuantityValid,double Quantity)
{
    if(!bQuantityValid || !FMath::IsFinite(Quantity) || Quantity<0) return EGHSInventoryState::Unknown;
    if(Name==TEXT("empty") && Quantity==0) return EGHSInventoryState::Empty;
    if(Name==TEXT("occupied") && Quantity>0) return EGHSInventoryState::Occupied;
    return EGHSInventoryState::Unknown;
}
}

bool FGHSInventoryMask::Set(int32 Slot,EGHSInventoryState State)
{
    if(Slot<0 || Slot>=36) return false;
    const int32 Word=Slot/18;const uint32 Bit=1u<<(Slot%18);
    uint32 Occupied=uint32(Values[Word]),Known=uint32(Values[Word+2]);
    Occupied&=~Bit;Known&=~Bit;
    if(State!=EGHSInventoryState::Unknown) Known|=Bit;
    if(State==EGHSInventoryState::Occupied) Occupied|=Bit;
    Values[Word]=float(Occupied);Values[Word+2]=float(Known);return true;
}
bool FGHSInventoryMask::IsKnown(int32 Slot) const
{ return Slot>=0 && Slot<36 && (uint32(Values[2+Slot/18])&(1u<<(Slot%18)))!=0; }
FBox GHSLocationInventory::EmptyPickBounds(const FBox& CargoBounds)
{
    if(!CargoBounds.IsValid) return CargoBounds;
    FBox Result=CargoBounds;Result.Max.Z=FMath::Min(Result.Max.Z,Result.Min.Z+4.);return Result;
}
FString FGHSLocationInventory::Key(const FString& CadId,int32 Level,int32 Column)
{ return CadId+FString::Printf(TEXT(":L%d:C%d"),Level,Column); }

TSharedRef<FGHSLocationInventory> FGHSLocationInventory::Shared()
{
    // One immutable export per game process. Changing files requires restarting the scene process.
    static TSharedRef<FGHSLocationInventory> Store=[]()
    {
        auto Result=MakeShared<FGHSLocationInventory>();FString Index,Mapping;
        const FString Data=FPaths::ProjectContentDir()/TEXT("GHSTwinUI/data");
        FFileHelper::LoadFileToString(Index,*(Data/TEXT("inventory/index.json")));
        FFileHelper::LoadFileToString(Mapping,*(Data/TEXT("inventory-bindings.json")));
        Result->Initialize(Index,Mapping,Data/TEXT("inventory"));return Result;
    }();
    return Store;
}

bool FGHSLocationInventory::Initialize(const FString& IndexText,const FString& BindingText,const FString& DataDirectory)
{
    bReady=false;Locations.Reset();Bindings.Reset();BindingConfidence.Reset();ExpectedInstances.Reset();Shards.Reset();ShardLRU.Reset();FailedShards.Reset();
    SnapshotId.Empty();Source.Reset();Error.Empty();Directory=DataDirectory;
    const auto Index=ParseInventory(IndexText),Mapping=ParseInventory(BindingText);
    const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Maps=nullptr;
    const TSharedPtr<FJsonObject>* SourceObject=nullptr;
    if(!VersionOne(Index) || !Warehouse108(Index) || !VersionOne(Mapping) || !Warehouse108(Mapping)
        || !Index->TryGetStringField(TEXT("snapshotId"),SnapshotId) || SnapshotId.IsEmpty()
        || !Index->TryGetObjectField(TEXT("source"),SourceObject) || !SourceObject || !SourceObject->IsValid()
        || !Index->TryGetArrayField(TEXT("locations"),Rows) || !Mapping->TryGetArrayField(TEXT("bindings"),Maps))
    { Error=TEXT("库存快照或库位映射无效");return false; }
    Source=*SourceObject;
    FString MappingSnapshot;
    if(Mapping->TryGetStringField(TEXT("snapshotId"),MappingSnapshot) && MappingSnapshot!=SnapshotId)
    { Error=TEXT("库存与映射快照不一致");return false; }
    if(Mapping->TryGetStringField(TEXT("sourceInventorySha256"),MappingSnapshot) && MappingSnapshot!=SnapshotId)
    { Error=TEXT("映射引用的库存源文件已变化");return false; }
    if(!Directory.IsEmpty() && !SourcesMatch(Mapping,Directory))
    { Error=TEXT("场景库位定义已变化，库存映射需重新生成");return false; }
    TSet<FString> InvalidIds,InvalidCodes;TMap<FString,FString> IdByCode;
    for(const auto& Value:*Rows)
    {
        const auto Row=Value->AsObject();FLocation Item;FString State;
        if(!Row || !Row->TryGetStringField(TEXT("id"),Item.Id) || Item.Id.IsEmpty()
            || !Row->TryGetStringField(TEXT("code"),Item.Code) || Item.Code.IsEmpty()
            || !Row->TryGetStringField(TEXT("shard"),Item.Shard) || !SafeShard(Item.Shard)
            || !Row->TryGetStringField(TEXT("state"),State)
            || !CountField(Row,TEXT("recordCount"),Item.RecordCount) || !CountField(Row,TEXT("skuCount"),Item.SkuCount))
        { if(!Item.Id.IsEmpty()) InvalidIds.Add(Item.Id);continue; }
        const bool bQuantity=Row->TryGetNumberField(TEXT("quantity"),Item.Quantity);
        const bool bAvailable=Row->TryGetNumberField(TEXT("availableQuantity"),Item.AvailableQuantity);
        Item.State=InventoryState(State,bQuantity && bAvailable && FMath::IsFinite(Item.AvailableQuantity),Item.Quantity);
        if(Locations.Contains(Item.Id)) InvalidIds.Add(Item.Id);
        if(const auto* Existing=IdByCode.Find(Item.Code)) {InvalidIds.Add(*Existing);InvalidIds.Add(Item.Id);InvalidCodes.Add(Item.Code);}
        IdByCode.Add(Item.Code,Item.Id);Locations.Add(Item.Id,MoveTemp(Item));
    }
    for(const FString& Id:InvalidIds) Locations.Remove(Id);
    TSet<FString> InvalidKeys,InvalidMappedIds,InvalidCad;TMap<FString,FString> KeyById;
    for(const auto& Value:*Maps)
    {
        const auto Row=Value->AsObject();FString Cad,Id,Code,Confidence,Evidence;int32 Level=0,Column=0;
        if(!Row || !Row->TryGetStringField(TEXT("cadId"),Cad) || !Cad.StartsWith(TEXT("CAD_"))
            || !Row->TryGetStringField(TEXT("locationId"),Id) || !Row->TryGetStringField(TEXT("locationCode"),Code)
            || !CountField(Row,TEXT("level"),Level) || !CountField(Row,TEXT("column"),Column)
            || Level>64 || Column>64 || ((Level==0)!=(Column==0))
            || !Row->TryGetStringField(TEXT("confidence"),Confidence)
            || (Confidence!=TEXT("rule_inferred") && Confidence!=TEXT("confirmed"))
            || !Row->TryGetStringField(TEXT("evidence"),Evidence) || Evidence.IsEmpty()) continue;
        const auto* Location=Locations.Find(Id);
        if(!Location || Location->Code!=Code || InvalidCodes.Contains(Code)) continue;
        FExpectedInstance Expected;FVector Position,Rotation,Scale;
        const bool bComplete=Row->TryGetStringField(TEXT("expectedMesh"),Expected.Mesh) && !Expected.Mesh.IsEmpty()
            && VectorField(Row,TEXT("expectedPositionM"),Position) && VectorField(Row,TEXT("expectedWorldRotationDeg"),Rotation)
            && VectorField(Row,TEXT("expectedWorldScale"),Scale) && Scale.X>0 && Scale.Y>0 && Scale.Z>0;
        if(!bComplete && !Directory.IsEmpty()) {InvalidCad.Add(Cad);continue;}
        if(bComplete)
        {
            Expected.Transform=FTransform(FRotator(Rotation.X,Rotation.Y,Rotation.Z),FVector(Position.X*100,-Position.Y*100,Position.Z*100),Scale);
            if(const auto* Previous=ExpectedInstances.Find(Cad); Previous &&
                (Previous->Mesh!=Expected.Mesh || !Previous->Transform.Equals(Expected.Transform,.0001))) InvalidCad.Add(Cad);
            ExpectedInstances.Add(Cad,Expected);
        }
        const FString SlotKey=Key(Cad,Level,Column);
        if(const FString* Existing=Bindings.Find(SlotKey)) {InvalidKeys.Add(SlotKey);InvalidMappedIds.Add(*Existing);InvalidMappedIds.Add(Id);}
        if(const FString* Existing=KeyById.Find(Id)) {InvalidKeys.Add(*Existing);InvalidKeys.Add(SlotKey);InvalidMappedIds.Add(Id);}
        Bindings.Add(SlotKey,Id);BindingConfidence.Add(SlotKey,Confidence);KeyById.Add(Id,SlotKey);
    }
    for(auto It=Bindings.CreateIterator();It;++It)
        if(InvalidKeys.Contains(It.Key()) || InvalidMappedIds.Contains(It.Value()) || InvalidCad.Contains(It.Key().Left(It.Key().Find(TEXT(":L"))))) It.RemoveCurrent();
    for(const auto& Cad:InvalidCad) ExpectedInstances.Remove(Cad);
    bReady=true;return true;
}

const FGHSLocationInventory::FLocation* FGHSLocationInventory::Find(const FString& CadId,int32 Level,int32 Column) const
{
    if(!bReady || CadId.IsEmpty()) return nullptr;
    const FString* Id=Bindings.Find(Key(CadId,Level,Column));return Id?Locations.Find(*Id):nullptr;
}
bool FGHSLocationInventory::MatchesTransform(const FString& CadId,const FString& Mesh,const FTransform& Transform) const
{
    const auto* Expected=ExpectedInstances.Find(CadId);
    return bReady && Expected && Expected->Mesh==Mesh && !Transform.ContainsNaN()
        && Transform.GetLocation().Equals(Expected->Transform.GetLocation(),.1)
        && Transform.GetScale3D().Equals(Expected->Transform.GetScale3D(),.0001)
        && Transform.GetRotation().Equals(Expected->Transform.GetRotation(),.0001);
}
const FGHSLocationInventory::FLocation* FGHSLocationInventory::FindForTransform(const FString& CadId,int32 Level,int32 Column,const FString& Mesh,const FTransform& Transform) const
{ return MatchesTransform(CadId,Mesh,Transform)?Find(CadId,Level,Column):nullptr; }

bool FGHSLocationInventory::AcceptShard(const FString& Name,const FString& Text) const
{
    if(!SafeShard(Name) || !bReady) return false;
    const auto Root=ParseInventory(Text);FString Snapshot;const TSharedPtr<FJsonObject>* Data=nullptr;
    if(!VersionOne(Root) || !Root->TryGetStringField(TEXT("snapshotId"),Snapshot) || Snapshot!=SnapshotId
        || !Root->TryGetObjectField(TEXT("locations"),Data) || !Data || !Data->IsValid())
    {FailedShards.Add(Name);Shards.Remove(Name);return false;}
    TMap<FString,TSharedPtr<FJsonObject>> Accepted;
    for(const auto& Entry:(*Data)->Values)
    {
        const auto Row=Entry.Value->AsObject();const auto* Summary=Locations.Find(FString(Entry.Key.ToView()));
        FString Id,Code,State;const TSharedPtr<FJsonObject>* Totals=nullptr;const TSharedPtr<FJsonObject>* Fields=nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Items=nullptr;double Quantity=0,Available=0;int32 Count=0,SkuCount=0;
        if(!Summary || Summary->Shard!=Name || !Warehouse108(Row)
            || !Row->TryGetStringField(TEXT("id"),Id) || Id!=Summary->Id
            || !Row->TryGetStringField(TEXT("code"),Code) || Code!=Summary->Code
            || !Row->TryGetStringField(TEXT("state"),State)
            || !Row->TryGetObjectField(TEXT("totals"),Totals) || !Totals || !Totals->IsValid()
            || !Row->TryGetObjectField(TEXT("fields"),Fields)
            || !Row->TryGetArrayField(TEXT("items"),Items)
            || !CountField(Row,TEXT("recordCount"),Count) || Count!=Summary->RecordCount || Count!=Items->Num()
            || !CountField(Row,TEXT("skuCount"),SkuCount) || SkuCount!=Summary->SkuCount
            || !(*Totals)->TryGetNumberField(TEXT("quantity"),Quantity) || !FMath::IsFinite(Quantity)
            || !(*Totals)->TryGetNumberField(TEXT("availableQuantity"),Available) || !FMath::IsFinite(Available)
            || Quantity!=Summary->Quantity || Available!=Summary->AvailableQuantity
            || InventoryState(State,true,Quantity)!=Summary->State) continue;
        Accepted.Add(Id,Row);
    }
    Shards.Add(Name,MoveTemp(Accepted));FailedShards.Remove(Name);ShardLRU.Remove(Name);ShardLRU.Add(Name);
    while(ShardLRU.Num()>8) {Shards.Remove(ShardLRU[0]);ShardLRU.RemoveAt(0);}
    return true;
}
const TSharedPtr<FJsonObject>* FGHSLocationInventory::Detail(const FLocation& Location) const
{
    if(!Shards.Contains(Location.Shard) && !FailedShards.Contains(Location.Shard))
    {
        FString Text;
        if(Directory.IsEmpty() || !FFileHelper::LoadFileToString(Text,*(Directory/Location.Shard)) || !AcceptShard(Location.Shard,Text)) FailedShards.Add(Location.Shard);
    }
    if(const auto* Shard=Shards.Find(Location.Shard)) {ShardLRU.Remove(Location.Shard);ShardLRU.Add(Location.Shard);return Shard->Find(Location.Id);}
    return nullptr;
}
TSharedRef<FJsonObject> FGHSLocationInventory::Selection(const FString& CadId,int32 Level,int32 Column) const
{
    const auto Result=MakeShared<FJsonObject>();Result->SetStringField(TEXT("snapshotId"),SnapshotId);
    if(Source) Result->SetObjectField(TEXT("source"),Source);
    const auto* Location=Find(CadId,Level,Column);
    if(!Location) {Result->SetStringField(TEXT("mappingStatus"),TEXT("unmapped"));return Result;}
    Result->SetStringField(TEXT("mappingConfidence"),BindingConfidence.FindRef(Key(CadId,Level,Column)));
    if(const auto* Object=Detail(*Location))
    {Result->SetStringField(TEXT("mappingStatus"),TEXT("mapped"));Result->SetObjectField(TEXT("location"),*Object);}
    else {Result->SetStringField(TEXT("mappingStatus"),TEXT("unknown"));Result->SetStringField(TEXT("note"),TEXT("库位已匹配，库存明细未通过快照校验"));}
    return Result;
}
