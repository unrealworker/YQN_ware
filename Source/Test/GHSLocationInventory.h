#pragma once
#include "CoreMinimal.h"

class FJsonObject;
enum class EGHSInventoryState : uint8 { Unknown, Empty, Occupied };

/** Four exact 18-bit words consumed by inventory materials at custom-data offsets 1..4. */
struct TEST_API FGHSInventoryMask
{
    float Values[4]={0,0,0,0};
    bool Set(int32 Slot,EGHSInventoryState State);
    bool IsKnown(int32 Slot) const;
};

namespace GHSLocationInventory
{
    TEST_API FBox EmptyPickBounds(const FBox& CargoBounds);
}

/** Immutable snapshot index, explicitly qualified CAD bindings and bounded on-demand detail cache.
 * No network requests and no per-frame parsing. IDs remain strings, including leading zeroes. */
class TEST_API FGHSLocationInventory
{
public:
    struct FLocation
    {
        FString Id,Code,Shard;
        EGHSInventoryState State=EGHSInventoryState::Unknown;
        double Quantity=0,AvailableQuantity=0;
        int32 RecordCount=0,SkuCount=0;
    };
    static TSharedRef<FGHSLocationInventory> Shared();
    bool Initialize(const FString& IndexText,const FString& BindingText,const FString& DataDirectory);
    const FLocation* Find(const FString& CadId,int32 Level,int32 Column) const;
    /** Only a complete current mesh/transform contract can affect scene geometry or picking. */
    bool MatchesTransform(const FString& CadId,const FString& Mesh,const FTransform& WorldTransform) const;
    const FLocation* FindForTransform(const FString& CadId,int32 Level,int32 Column,const FString& Mesh,const FTransform& WorldTransform) const;
    /** Always returns an inventory envelope; missing/invalid mapping is explicitly unknown. */
    TSharedRef<FJsonObject> Selection(const FString& CadId,int32 Level,int32 Column) const;
    /** Validates a shard before caching; exposed for deterministic import and regression tests. */
    bool AcceptShard(const FString& Name,const FString& Text) const;
    const FString& GetSnapshotId() const { return SnapshotId; }
    const FString& GetError() const { return Error; }
    int32 NumBindings() const { return Bindings.Num(); }
    int32 NumLocations() const { return Locations.Num(); }
    bool IsReady() const { return bReady; }
private:
    static FString Key(const FString& CadId,int32 Level,int32 Column);
    const TSharedPtr<FJsonObject>* Detail(const FLocation& Location) const;
    FString Directory,SnapshotId,Error;
    TSharedPtr<FJsonObject> Source;
    TMap<FString,FLocation> Locations;
    TMap<FString,FString> Bindings;
    TMap<FString,FString> BindingConfidence;
    struct FExpectedInstance { FString Mesh; FTransform Transform; };
    TMap<FString,FExpectedInstance> ExpectedInstances;
    mutable TMap<FString,TMap<FString,TSharedPtr<FJsonObject>>> Shards;
    mutable TArray<FString> ShardLRU;
    mutable TSet<FString> FailedShards;
    bool bReady=false;
};
