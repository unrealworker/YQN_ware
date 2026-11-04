#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "EnvironmentRenderProfile.generated.h"

/** Optional per-map profile. No actor in a map means no renderer override. */
UCLASS(NotBlueprintable)
class TEST_API AEnvironmentRenderProfile : public AActor
{
    GENERATED_BODY()

public:
    AEnvironmentRenderProfile();

    /** Global-SDF inner clipmap half extent in centimetres; active profiles use their maximum. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Environment Rendering",
        meta=(ClampMin="1.0", UIMin="1000.0", UIMax="20000.0", Units="cm"))
    float LumenClipmapExtent = 5000.f;

    UFUNCTION(BlueprintCallable, Category="Environment Rendering")
    void SetLumenClipmapExtent(float NewExtent);

    virtual void PostRegisterAllComponents() override;
    virtual void PostUnregisterAllComponents() override;
    virtual void Destroyed() override;
    virtual void BeginDestroy() override;

#if WITH_EDITOR
    virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
    virtual void PostEditUndo() override;
#endif

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    void RefreshProfile();
    void ReleaseProfile();
    void OnWorldCleanup(UWorld* World, bool bSessionEnded, bool bCleanupResources);

    FDelegateHandle WorldCleanupHandle;
    bool bOwnsLease = false;
    bool bEndedPlay = false;
    bool bWorldCleanupStarted = false;
};
