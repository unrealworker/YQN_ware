#pragma once

#include "CoreMinimal.h"
#include "Components/InstancedStaticMeshComponent.h"

// Entire carts are usually docked. Keep their existing slots and update only
// transforms that changed; callers group render-state notification per component.
struct FMPRCartInstanceTransformCache
{
    void Reset()
    {
        LastComponent.Reset(); LastInstanceIndex = INDEX_NONE;
    }

    bool Submit(UInstancedStaticMeshComponent* Component, int32 InstanceIndex, const FTransform& World)
    {
        if (!Component || InstanceIndex < 0 || InstanceIndex >= Component->GetInstanceCount()) return false;
        if (LastComponent.Get() == Component && LastInstanceIndex == InstanceIndex && LastWorld.Equals(World, 1.e-9)
            && LastComponentWorld.Equals(Component->GetComponentTransform(), 1.e-9))
            return false;
        if (!Component->UpdateInstanceTransform(InstanceIndex, World, true, false, true)) return false;
        LastWorld = World; LastComponentWorld = Component->GetComponentTransform();
        LastComponent = Component; LastInstanceIndex = InstanceIndex;
        return true;
    }

private:
    FTransform LastWorld = FTransform::Identity;
    FTransform LastComponentWorld = FTransform::Identity;
    TWeakObjectPtr<UInstancedStaticMeshComponent> LastComponent;
    int32 LastInstanceIndex = INDEX_NONE;
};

// ISM components stay fixed while their instances move. GPU Scene needs the
// previous instance pose, not just the (stationary) component's previous pose.
struct FMPRInstanceMotionHistory
{
    void Reset()
    {
        LastWorld.Reset(); PreviousWorld.Reset(); LastIdentities.Reset();
        LastFrame = MAX_uint64;
    }

    bool Submit(UInstancedStaticMeshComponent* Component, const TArray<FTransform>& CurrentWorld,
        uint64 FrameNumber, const TArray<uint64>& Identities = {})
    {
        if (!Component || CurrentWorld.Num() != Component->GetInstanceCount()
            || (!Identities.IsEmpty() && Identities.Num() != CurrentWorld.Num())) return false;
        if (CurrentWorld.IsEmpty()) return true;

        const bool First = LastWorld.Num() != CurrentWorld.Num();
        if (First) PreviousWorld = CurrentWorld;
        else if (FrameNumber != LastFrame) PreviousWorld = LastWorld;

        for (int32 I = 0; I < CurrentWorld.Num(); ++I)
        {
            const bool Visible = !CurrentWorld[I].GetScale3D().IsNearlyZero();
            const bool WasVisible = !First && !LastWorld[I].GetScale3D().IsNearlyZero();
            const bool NewIdentity = !Identities.IsEmpty()
                && (!LastIdentities.IsValidIndex(I) || LastIdentities[I] != Identities[I]);
            // A newly shown/reused slot has no physical motion from the hidden
            // origin (or the previous parcel's location).
            if (First || !Visible || !WasVisible || NewIdentity) PreviousWorld[I] = CurrentWorld[I];
        }

        Component->SetHasPerInstancePrevTransforms(true);
        // TransformChanged schedules the incremental instance upload itself.
        // Recreating the scene proxy here would discard its temporal history.
        const bool Updated = Component->BatchUpdateInstancesTransforms(
            0, CurrentWorld, PreviousWorld, true, false, true);
        if (Updated)
        {
            LastWorld = CurrentWorld; LastIdentities = Identities; LastFrame = FrameNumber;
        }
        return Updated;
    }

private:
    TArray<FTransform> LastWorld, PreviousWorld;
    TArray<uint64> LastIdentities;
    uint64 LastFrame = MAX_uint64;
};
