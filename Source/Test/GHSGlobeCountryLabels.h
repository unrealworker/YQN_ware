#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GHSGlobeCountryLabels.generated.h"

class UDecalComponent;

/** Country typography projected onto Earth, with a geographic north-up tangent frame. */
UCLASS(NotBlueprintable, Transient)
class TEST_API AGHSGlobeCountryLabels : public AActor
{
    GENERATED_BODY()
public:
    AGHSGlobeCountryLabels();
    void Initialize(AActor* GlobeRoot, float GlobeRadius);

private:
    UPROPERTY(Transient) TArray<TObjectPtr<UDecalComponent>> Labels;
};
