#pragma once

#include "CoreMinimal.h"

class APlayerController;
class UWorld;

struct TEST_API FGHSTwinPoint
{
    FString Id, Title, Kind, Status;
    FVector Location = FVector::ZeroVector;
    bool bAlert = false;
};

/** Shared identity and geometric selection rules, independent of collision settings. */
namespace GHSTwinSelection
{
    struct TEST_API FIdentity
    {
        FString Id, Type, Title, DockId;
    };
    TEST_API bool Identify(const TArray<FName>& Tags, FIdentity& Out);
    /** Runtime-only legacy HUD setup. Reconciles copied forklift IDs, adds missing data components,
     * and seeds demo data only on newly created forklift/stacker components. Returns creations. */
    TEST_API int32 BootstrapComponents(UWorld* World);
    /** Distance is in world centimetres, including for scaled and rotated instances. */
    TEST_API bool IntersectBox(const FVector& Origin, const FVector& Direction,
        const FTransform& Transform, const FBox& LocalBounds, double& OutDistance,
        FVector* OutLocalHit = nullptr);
}

/** Read-only scene discovery and telemetry adapter. Only ApplyLayers changes runtime visibility. */
class TEST_API FGHSTwinSceneData
{
public:
    FGHSTwinSceneData();
    ~FGHSTwinSceneData();
    FGHSTwinSceneData(const FGHSTwinSceneData&) = delete;
    FGHSTwinSceneData& operator=(const FGHSTwinSceneData&) = delete;

    void Refresh(UWorld* World);
    FString SnapshotJson(const FString& SelectedId = TEXT("")) const;
    bool Resolve(const FString& Id, FVector& OutLocation, FVector& OutExtent) const;
    /** Bounds of actual storage geometry, for area views rather than instance selection. */
    bool RegionBounds(const FString& Region, FVector& OutLocation, FVector& OutExtent) const;
    bool Pick(APlayerController* Controller, const FVector2D& ScreenPosition, FString& OutId);
    /** The same scene selection for a world ray, also usable by non-mouse input. */
    bool PickRay(const FVector& Origin, const FVector& Direction, FString& OutId);
    TArray<FGHSTwinPoint> Points() const;
    void ApplyLayers(bool Equipment, bool Racks);

private:
    struct FImpl;
    TUniquePtr<FImpl> Impl;
};
