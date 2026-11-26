#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "GHSRoadMarkingEditorLibrary.generated.h"

class UMaterialInterface;
class UStaticMesh;

UCLASS()
class TEST_API UGHSRoadMarkingEditorLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
#if WITH_EDITOR
    /** Add signed edge offsets and a dedicated paint section to the matched road triangles in LOD0. */
    UFUNCTION(BlueprintCallable, Category="GHS|Editor")
    static bool ApplyRoadRibbonUV(UStaticMesh* Mesh, const FString& ManifestPath, UMaterialInterface* Material, int32 UVChannel);
#endif
};
