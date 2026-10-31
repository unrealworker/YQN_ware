#include "GHSWarehouseRegistry.h"
#include "Dom/JsonObject.h"
#include "Misc/PackageName.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
bool Number(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,double& Value)
{return O->TryGetNumberField(Key,Value)&&FMath::IsFinite(Value);}
}
bool GHSGlobe::ValidCoordinates(double Lat,double Lon)
{return FMath::IsFinite(Lat)&&FMath::IsFinite(Lon)&&Lat>=-90&&Lat<=90&&Lon>=-180&&Lon<=180;}
FVector GHSGlobe::ToSphere(double Lat,double Lon,double Radius)
{
    if(!ValidCoordinates(Lat,Lon)||!FMath::IsFinite(Radius)||Radius<=0)return FVector::ZeroVector;
    const double A=FMath::DegreesToRadians(Lat),B=FMath::DegreesToRadians(Lon);
    // FBX converts Blender's right-handed canonical globe to UE by reflecting Y.
    // Match that imported geometry: east longitudes point toward local -Y.
    return Radius*FVector(FMath::Cos(A)*FMath::Cos(B),-FMath::Cos(A)*FMath::Sin(B),FMath::Sin(A));
}
bool GHSGlobe::IsSurfaceVisible(FVector Point,FVector Camera,FVector Center)
{return FVector::DotProduct(Point-Center,Camera-Point)>0;}
bool GHSGlobe::IsAllowedMap(const FString& Map)
{return Map.StartsWith(TEXT("/Game/Maps/"))&&!Map.Contains(TEXT(".."))&&FPackageName::IsValidLongPackageName(Map);}
bool GHSGlobe::ParseCatalog(const FString& Json,TArray<FGHSGlobeWarehouse>& Out,FString& Error)
{
    Out.Empty();Error.Empty();TSharedPtr<FJsonObject> Root;const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;double Schema=0;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json),Root)||!Root||!Number(Root,TEXT("schemaVersion"),Schema)||Schema!=2||!Root->TryGetArrayField(TEXT("warehouses"),Rows)||Rows->Num()>2000)
    {Error=TEXT("仓库目录需要 schemaVersion 2，且条目数不能超过 2000");return false;}
    TSet<FString> Ids;TArray<FGHSGlobeWarehouse> Parsed;
    for(const auto& Row:*Rows)
    {
        const auto O=Row->AsObject();FGHSGlobeWarehouse W;
        if(!O||!O->TryGetStringField(TEXT("id"),W.Id)||W.Id.IsEmpty()||W.Id.Len()>80||Ids.Contains(W.Id)
            ||!O->TryGetStringField(TEXT("name"),W.Name)||W.Name.IsEmpty()
            ||!Number(O,TEXT("latitude"),W.Latitude)||!Number(O,TEXT("longitude"),W.Longitude)
            ||!ValidCoordinates(W.Latitude,W.Longitude)||!O->TryGetStringField(TEXT("map"),W.Map)||!IsAllowedMap(W.Map))
        {Error=TEXT("仓库目录含重复标识、无效经纬度或地图路径");return false;}
        // These case-sensitive prefixes belong to native/browser aggregate markers.
        if(W.Id.StartsWith(TEXT("cluster-"),ESearchCase::CaseSensitive)||W.Id.StartsWith(TEXT("cluster:"),ESearchCase::CaseSensitive))
        {Error=TEXT("仓库 id 不能使用保留前缀 cluster- 或 cluster:（区分大小写）");return false;}
        if(!O->TryGetStringField(TEXT("runtimeProfile"),W.RuntimeProfile)||(W.RuntimeProfile!=TEXT("ghs")&&W.RuntimeProfile!=TEXT("generic")))
        {Error=TEXT("仓库 runtimeProfile 必须明确为 ghs 或 generic");return false;}
        const TArray<TSharedPtr<FJsonValue>>* Features=nullptr;
        if(!O->TryGetArrayField(TEXT("features"),Features)){Error=TEXT("仓库缺少 features 数组");return false;}
        for(const auto& F:*Features)
        {
            FString Feature;
            if(!F->TryGetString(Feature)||W.RuntimeProfile==TEXT("generic")||(Feature!=TEXT("warehouse-ui")&&Feature!=TEXT("traffic"))||W.Features.Contains(Feature))
            {Error=TEXT("仓库 features 包含未实现、不兼容或重复的能力");return false;}
            W.Features.Add(Feature);
        }
        if(W.RuntimeProfile==TEXT("ghs")&&!W.Features.Contains(TEXT("warehouse-ui")))
        {Error=TEXT("ghs profile 需要 warehouse-ui 能力");return false;}
        O->TryGetStringField(TEXT("city"),W.City);O->TryGetStringField(TEXT("address"),W.Address);O->TryGetStringField(TEXT("thumbnail"),W.Thumbnail);
        if(!O->TryGetStringField(TEXT("cityShort"),W.CityShort)||W.CityShort.IsEmpty())W.CityShort=W.City;
        O->TryGetStringField(TEXT("region"),W.Region);O->TryGetStringField(TEXT("country"),W.Country);
        const TSharedPtr<FJsonObject>* Pose=nullptr;
        if(O->TryGetObjectField(TEXT("entryCamera"),Pose))
        {
            double X,Y,Z,Distance,Pitch,Yaw;
            if(!Number(*Pose,TEXT("x"),X)||!Number(*Pose,TEXT("y"),Y)||!Number(*Pose,TEXT("z"),Z)||!Number(*Pose,TEXT("distance"),Distance)||!Number(*Pose,TEXT("pitch"),Pitch)||!Number(*Pose,TEXT("yaw"),Yaw)
                ||Distance<900||Distance>95000||Pitch<-80||Pitch>-15||FMath::Abs(X)>1.e8||FMath::Abs(Y)>1.e8||FMath::Abs(Z)>1.e8)
            {Error=TEXT("entryCamera 参数无效");return false;}
            W.EntryPivot=FVector(X,Y,Z);W.EntryDistance=float(Distance);W.EntryRotation=FRotator(Pitch,Yaw,0);
        }
        else if(W.RuntimeProfile==TEXT("generic")){Error=TEXT("generic profile 必须提供地图专属 entryCamera");return false;}
        W.UnitPosition=ToSphere(W.Latitude,W.Longitude,1);
        Ids.Add(W.Id);Parsed.Add(MoveTemp(W));
    }
    Out=MoveTemp(Parsed);return true;
}
bool FGHSWarehouseRegistry::Load(const FString& Json,FString& Error)
{
    TArray<FGHSGlobeWarehouse> NewEntries;if(!GHSGlobe::ParseCatalog(Json,NewEntries,Error))return false;
    TArray<TSharedPtr<FJsonValue>> Rows;TMap<FString,int32> NewIndices;
    for(int32 Index=0;Index<NewEntries.Num();++Index)
    {
        const auto& W=NewEntries[Index];NewIndices.Add(W.Id,Index);auto O=MakeShared<FJsonObject>();
        O->SetStringField(TEXT("id"),W.Id);O->SetStringField(TEXT("name"),W.Name);O->SetStringField(TEXT("city"),W.City);O->SetStringField(TEXT("address"),W.Address);
        O->SetStringField(TEXT("cityShort"),W.CityShort);
        O->SetStringField(TEXT("region"),W.Region);O->SetStringField(TEXT("country"),W.Country);O->SetStringField(TEXT("map"),W.Map);O->SetStringField(TEXT("thumbnail"),W.Thumbnail);
        O->SetStringField(TEXT("runtimeProfile"),W.RuntimeProfile);O->SetNumberField(TEXT("latitude"),W.Latitude);O->SetNumberField(TEXT("longitude"),W.Longitude);
        TArray<TSharedPtr<FJsonValue>> Features;for(const auto& F:W.Features)Features.Add(MakeShared<FJsonValueString>(F));O->SetArrayField(TEXT("features"),Features);
        O->SetField(TEXT("inventory"),MakeShared<FJsonValueNull>());O->SetField(TEXT("occupancy"),MakeShared<FJsonValueNull>());Rows.Add(MakeShared<FJsonValueObject>(O));
    }
    FString NewJson;FJsonSerializer::Serialize(Rows,TJsonWriterFactory<>::Create(&NewJson));
    Entries=MoveTemp(NewEntries);Indices=MoveTemp(NewIndices);CatalogJson=MoveTemp(NewJson);++Revision;return true;
}
const FGHSGlobeWarehouse* FGHSWarehouseRegistry::Find(const FString& Id)const
{const int32* Index=Indices.Find(Id);return Index?&Entries[*Index]:nullptr;}

TArray<FGHSWarehousePOICluster> GHSClusterWarehousePoints(const TArray<FGHSWarehouseProjectedPoint>& Points,const FString& SelectedId,int32 Budget)
{
    Budget=FMath::Clamp(Budget,2,256);TArray<FGHSWarehousePOICluster> Result;
    const auto ValidPoint=[](const auto& P){return FMath::IsFinite(P.Position.X)&&FMath::IsFinite(P.Position.Y)&&P.Position.X>=0&&P.Position.Y>=0&&P.Position.X<=20000&&P.Position.Y<=20000;};
    const auto* Selected=Points.FindByPredicate([&](const auto& P){return P.Id==SelectedId&&ValidPoint(P);});
    if(Selected)Result.Add({Selected->Id,{Selected->Id},Selected->Position});
    TMap<FIntPoint,TArray<int32>> Cells;int32 CellSize=64;
    for(;;)
    {
        Cells.Reset();
        for(int32 Index=0;Index<Points.Num();++Index)
        {
            const auto& P=Points[Index];if(P.Id==SelectedId||!ValidPoint(P))continue;
            Cells.FindOrAdd(FIntPoint(FMath::FloorToInt(P.Position.X/CellSize),FMath::FloorToInt(P.Position.Y/CellSize))).Add(Index);
        }
        if(Cells.Num()+Result.Num()<=Budget)break;
        CellSize*=2;
    }
    TArray<FIntPoint> Keys;Cells.GetKeys(Keys);Keys.Sort([](const auto& A,const auto& B){return A.X==B.X?A.Y<B.Y:A.X<B.X;});
    for(const auto Key:Keys)
    {
        const auto& Indices=Cells[Key];FGHSWarehousePOICluster Cluster;
        for(int32 Index:Indices){Cluster.Ids.Add(Points[Index].Id);Cluster.Position+=Points[Index].Position;}
        Cluster.Position/=Indices.Num();
        Cluster.Id=Indices.Num()==1?Cluster.Ids[0]:FString::Printf(TEXT("cluster:%d:%d:%d"),CellSize,Key.X,Key.Y);
        Result.Add(MoveTemp(Cluster));
    }
    return Result;
}
