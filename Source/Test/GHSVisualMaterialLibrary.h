#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GHSVisualMaterialLibrary.generated.h"

class UMaterial;
class UMaterialExpression;

/** Narrow editor authoring access for GHS visual-polish materials and the replay trail. */
UCLASS()
class TEST_API UGHSVisualMaterialLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Connect output zero to WPO. Does not compile or save the material. */
    UFUNCTION(BlueprintCallable, Category="GHS|Editor Materials")
    static bool ConnectWorldPositionOffset(UMaterial* Material, UMaterialExpression* Expression);

    /** Read whether the owned material has a valid, locally owned WPO input. */
    UFUNCTION(BlueprintPure, Category="GHS|Editor Materials")
    static bool HasWorldPositionOffset(UMaterial* Material);
};
