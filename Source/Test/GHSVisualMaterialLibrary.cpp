#include "GHSVisualMaterialLibrary.h"

#include "Materials/Material.h"
#include "Materials/MaterialExpression.h"

namespace
{
bool IsOwnedVisualMaterial(const UMaterial* Material)
{
    return IsValid(Material) && Material->GetPathName().StartsWith(
        TEXT("/Game/GHSZcoolSmartFactory/VisualPolish/"));
}
}

bool UGHSVisualMaterialLibrary::ConnectWorldPositionOffset(
    UMaterial* Material, UMaterialExpression* Expression)
{
#if WITH_EDITOR
    if (!IsOwnedVisualMaterial(Material) || !IsValid(Expression)
        || Expression->GetOuter() != Material || Expression->GetOutputs().IsEmpty())
    {
        return false;
    }
    UMaterialEditorOnlyData* Data = Material->GetEditorOnlyData();
    if (!Data)
    {
        return false;
    }
    Material->Modify();
    Data->Modify();
    Data->WorldPositionOffset.Connect(0, Expression);
    Data->WorldPositionOffset.UseConstant = false;
    Material->MarkPackageDirty();
    return Data->WorldPositionOffset.Expression == Expression
        && Data->WorldPositionOffset.OutputIndex == 0;
#else
    return false;
#endif
}

bool UGHSVisualMaterialLibrary::HasWorldPositionOffset(UMaterial* Material)
{
#if WITH_EDITOR
    if (!IsOwnedVisualMaterial(Material))
    {
        return false;
    }
    const UMaterialEditorOnlyData* Data = Material->GetEditorOnlyData();
    return Data && IsValid(Data->WorldPositionOffset.Expression)
        && Data->WorldPositionOffset.Expression->GetOuter() == Material
        && Data->WorldPositionOffset.OutputIndex == 0
        && !Data->WorldPositionOffset.UseConstant;
#else
    return false;
#endif
}
