#pragma once
#include "CoreMinimal.h"

/** Stable warehouse identity and capabilities; no UE world or UI dependencies. */
struct FGHSGlobeWarehouse
{
    FString Id,Name,City,CityShort,Address,Map,Thumbnail,Region,Country,RuntimeProfile;
    TArray<FString> Features;
    double Latitude=0,Longitude=0;
    FVector EntryPivot=FVector(-646.665,833.981,0);
    float EntryDistance=53500.f;
    FRotator EntryRotation=FRotator(-30,-90,0);
    FVector UnitPosition=FVector::ZeroVector;
};
namespace GHSGlobe
{
    TEST_API bool ValidCoordinates(double Latitude,double Longitude);
    TEST_API FVector ToSphere(double Latitude,double Longitude,double Radius);
    TEST_API bool IsSurfaceVisible(FVector Point,FVector Camera,FVector Center);
    TEST_API bool IsAllowedMap(const FString& Map);
    TEST_API bool ParseCatalog(const FString& Json,TArray<FGHSGlobeWarehouse>& Out,FString& Error);
}

/** Atomically validated catalog, O(1) identity lookups, and one cached static payload per revision. */
class TEST_API FGHSWarehouseRegistry
{
public:
    bool Load(const FString& Json,FString& Error);
    const TArray<FGHSGlobeWarehouse>& GetEntries()const{return Entries;}
    const FGHSGlobeWarehouse* Find(const FString& Id)const;
    const FString& GetCatalogJson()const{return CatalogJson;}
    uint64 GetRevision()const{return Revision;}
private:
    TArray<FGHSGlobeWarehouse> Entries;
    TMap<FString,int32> Indices;
    FString CatalogJson=TEXT("[]");
    uint64 Revision=0;
};

/** Never start another destination until the old level has fully left the world. */
struct FGHSWarehouseStreamPolicy
{
    static bool CanStart(bool HasDestination,bool Unloading){return !HasDestination&&!Unloading;}
    static bool FinishedUnloading(bool IsLoaded,bool IsInWorldList){return !IsLoaded&&!IsInWorldList;}
    // A level may mark itself invisible before incremental component removal finishes.
    static bool CanRevealGlobe(bool IsVisible,bool IsRemoving,bool IsInActiveWorldList)
    {return !IsVisible&&!IsRemoving&&!IsInActiveWorldList;}
};

struct FGHSWarehouseProjectedPoint { FString Id;FVector2D Position=FVector2D::ZeroVector; };
struct FGHSWarehousePOICluster
{
    FString Id;
    TArray<FString> Ids;
    FVector2D Position=FVector2D::ZeroVector;
};
/** Deterministic screen grid; budget limits labels, never silently drops a member warehouse. */
TEST_API TArray<FGHSWarehousePOICluster> GHSClusterWarehousePoints(
    const TArray<FGHSWarehouseProjectedPoint>& Points,const FString& SelectedId,int32 Budget=256);
