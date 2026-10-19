#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GHSMannedForkliftIdentityLibrary.generated.h"

class UWorld;
class AActor;

/** Identity repair for individually placed instances of the approved manual-forklift mesh. */
UCLASS()
class TEST_API UGHSMannedForkliftIdentityLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /**
     * Adds missing manual-forklift identity tags and assigns copied vehicles new IDs.
     * Returns the number of changed vehicle actors. In an editor world this marks the map dirty;
     * callers explicitly save it. Does not save assets or alter transforms. Foreign TwinIds are skipped.
     */
    UFUNCTION(BlueprintCallable, Category="Manned Forklift|Identity", meta=(WorldContext="WorldContextObject"))
    static int32 ReconcileWorld(UObject* WorldContextObject);

    /** Same operation on an explicit discovery list, useful to verify order independence. */
    static int32 ReconcileActors(UWorld* World, const TArray<AActor*>& Actors);
    static const TCHAR* GetApprovedMeshPath();
    static bool IsSupportedActor(AActor* Actor);
};
