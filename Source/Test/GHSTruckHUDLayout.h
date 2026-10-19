#pragma once

#include "CoreMinimal.h"

namespace GHSTruckHUDLayout
{
inline constexpr int32 GridColumns = 2;
inline constexpr int32 GridRows = 2;

struct FItem
{
    FString Id;
    FVector2D Anchor;
    FVector2D Size;
    /** Only items of the same equipment type can aggregate; empty keeps legacy behavior. */
    FString EquipmentType;
};

struct FGroup
{
    FString Key;
    TArray<FString> Members;
    FVector2D Anchor;
    FVector2D Size;
    FVector2D Position;
    /** Row-major index in the current adaptive 2x2 screen grid. */
    int32 CellIndex = INDEX_NONE;
    FString EquipmentType;
};

/** Stable screen-space topology. The widget owns visual interpolation and selection. */
class TEST_API FClusterer
{
public:
    const TArray<FGroup>& Update(const TArray<FItem>& Items, FVector2D Canvas, float DeltaSeconds, bool bAggregate = true);
    void Reset();

private:
    struct FAssignment
    {
        FString Id;
        int32 CellIndex = INDEX_NONE;
        int32 PendingCellIndex = INDEX_NONE;
        float PendingSeconds = 0.0f;
    };
    struct FLocalPlacement
    {
        double OffsetY = 0.0;
        bool bLocked = false;
    };

    TArray<FGroup> Groups;
    TArray<FAssignment> Assignments;
    TMap<FString,FLocalPlacement> LocalPlacements;
    FVector2D PreviousCanvas = FVector2D::ZeroVector;
};
}
