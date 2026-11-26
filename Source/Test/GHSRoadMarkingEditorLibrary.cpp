#include "GHSRoadMarkingEditorLibrary.h"

#if WITH_EDITOR
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "MeshDescription.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "StaticMeshAttributes.h"
#include "StaticMeshResources.h"

namespace
{
const FName RibbonSlot(TEXT("GHSRoadRibbon"));
// Render LOD0 and its source share float coordinates. The smallest marked segments are 0.018 cm long.
constexpr float PositionToleranceCm = 0.002f;

struct FRibbonTriangle
{
    FVector3f Points[3];
    FVector2f Offsets[3];
};

bool Fail(const UStaticMesh* Mesh, const FString& Reason)
{
    UE_LOG(LogTemp, Error, TEXT("GHS road markings [%s]: %s"), *GetNameSafe(Mesh), *Reason);
    return false;
}

bool LoadRibbon(const FString& Path, const FString& MeshName, TArray<FRibbonTriangle>& Triangles)
{
    FString Text, Name;
    TSharedPtr<FJsonObject> Json;
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!FFileHelper::LoadFileToString(Text, *Path) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) || !Json.IsValid() ||
        !Json->TryGetStringField(TEXT("mesh"), Name) || Name != MeshName ||
        !Json->TryGetArrayField(TEXT("triangles"), Rows) || Rows->IsEmpty())
    {
        return false;
    }
    for (const auto& Row : *Rows)
    {
        const TArray<TSharedPtr<FJsonValue>>* Corners = nullptr;
        if (!Row->TryGetArray(Corners) || Corners->Num() != 3) return false;
        FRibbonTriangle& Triangle = Triangles.AddDefaulted_GetRef();
        for (int32 Corner = 0; Corner < 3; ++Corner)
        {
            const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
            if (!(*Corners)[Corner]->TryGetArray(Values) || Values->Num() != 5) return false;
            float V[5];
            for (int32 I = 0; I < 5; ++I)
            {
                if (!(*Values)[I]->TryGetNumber(V[I]) || !FMath::IsFinite(V[I])) return false;
            }
            Triangle.Points[Corner] = FVector3f(V[0], V[1], V[2]);
            Triangle.Offsets[Corner] = FVector2f(V[3], V[4]);
        }
    }
    return true;
}

int32 Bucket(const FVector3f (&Points)[3])
{
    return FMath::FloorToInt((Points[0].X + Points[1].X + Points[2].X) / 3.f);
}

bool MatchCorners(const FVector3f (&Actual)[3], const FRibbonTriangle& Expected, int32 (&Order)[3])
{
    uint8 Used = 0;
    for (int32 A = 0; A < 3; ++A)
    {
        int32 E = 0;
        while (E < 3 && ((Used & (1 << E)) || !Actual[A].Equals(Expected.Points[E], PositionToleranceCm))) ++E;
        if (E == 3) return false;
        Order[A] = E;
        Used |= 1 << E;
    }
    return true;
}
}

bool UGHSRoadMarkingEditorLibrary::ApplyRoadRibbonUV(UStaticMesh* Mesh, const FString& ManifestPath,
                                                     UMaterialInterface* Material, int32 UVChannel)
{
    if (!Mesh || !Material || UVChannel < 1 || UVChannel >= MAX_STATIC_TEXCOORDS ||
        Mesh->GetNumSourceModels() < 1)
    {
        return Fail(Mesh, TEXT("Expected a source mesh, ribbon material and a spare UV channel."));
    }
    TArray<FRibbonTriangle> Manifest;
    if (!LoadRibbon(ManifestPath, Mesh->GetName(), Manifest))
    {
        return Fail(Mesh, FString::Printf(TEXT("Invalid triangle manifest or different mesh in %s"), *ManifestPath));
    }
    FMeshDescription* Description = Mesh->GetMeshDescription(0);
    if (!Description) return Fail(Mesh, TEXT("Missing LOD0 mesh description."));
    FStaticMeshAttributes Attributes(*Description);
    auto UVs = Attributes.GetVertexInstanceUVs();
    auto Names = Attributes.GetPolygonGroupMaterialSlotNames();
    const auto Positions = Attributes.GetVertexPositions();
    const FMeshBuildSettings& Settings = Mesh->GetSourceModel(0).BuildSettings;
    if (Settings.bGenerateLightmapUVs && Settings.DstLightmapIndex == UVChannel)
    {
        return Fail(Mesh, TEXT("Channel is reserved for generated lightmap UVs."));
    }
    FPolygonGroupID RibbonGroup(INDEX_NONE);
    for (FPolygonGroupID Group : Description->PolygonGroups().GetElementIDs())
    {
        if (Names[Group] == RibbonSlot) RibbonGroup = Group;
    }
    const int32 ExistingSlot = Mesh->GetMaterialIndex(RibbonSlot);
    const bool bInstalled = ExistingSlot != INDEX_NONE;
    if (bInstalled != (RibbonGroup.GetValue() != INDEX_NONE) ||
        (bInstalled && (Mesh->GetMaterial(ExistingSlot) != Material || UVChannel >= UVs.GetNumChannels())) ||
        (!bInstalled && UVChannel < UVs.GetNumChannels()))
    {
        return Fail(Mesh, TEXT("The requested UV channel or material slot is already in use."));
    }

    TMultiMap<int32, int32> Candidates;
    for (int32 I = 0; I < Manifest.Num(); ++I) Candidates.Add(Bucket(Manifest[I].Points), I);
    TSet<int32> Found;
    TSet<FTriangleID> RibbonFaces;
    TSet<FPolygonID> RibbonPolygons;
    TMap<FVertexInstanceID, FVector2f> Offsets;
    for (FTriangleID Face : Description->Triangles().GetElementIDs())
    {
        const auto Corners = Description->GetTriangleVertexInstances(Face);
        FVector3f Points[3];
        for (int32 I = 0; I < 3; ++I)
        {
            Points[I] = Positions[Description->GetVertexInstanceVertex(Corners[I])] * FVector3f(Settings.BuildScale3D);
        }
        const int32 X = Bucket(Points);
        for (int32 Key = X - 1; Key <= X + 1; ++Key)
        {
            for (auto It = Candidates.CreateConstKeyIterator(Key); It; ++It)
            {
                const int32 Index = It.Value();
                int32 Order[3];
                if (!MatchCorners(Points, Manifest[Index], Order)) continue;
                if (Found.Contains(Index) || RibbonFaces.Contains(Face))
                {
                    return Fail(Mesh, TEXT("Overlapping or duplicate target triangle."));
                }
                Found.Add(Index);
                RibbonFaces.Add(Face);
                RibbonPolygons.Add(Description->GetTrianglePolygon(Face));
                for (int32 I = 0; I < 3; ++I)
                {
                    const FVector2f Offset = Manifest[Index].Offsets[Order[I]];
                    const FVector2f* Previous = Offsets.Find(Corners[I]);
                    if (Previous && !Previous->Equals(Offset, KINDA_SMALL_NUMBER))
                    {
                        return Fail(Mesh, TEXT("Inconsistent signed offsets at a shared ribbon corner."));
                    }
                    Offsets.Add(Corners[I], Offset);
                }
            }
        }
    }
    if (Found.Num() != Manifest.Num())
    {
        return Fail(Mesh, FString::Printf(TEXT("Matched %d of %d triangles."), Found.Num(), Manifest.Num()));
    }
    // Complete the topology and repeat-run checks before mutating the source asset.
    for (FTriangleID Face : Description->Triangles().GetElementIDs())
    {
        const bool bTarget = RibbonFaces.Contains(Face);
        if (RibbonPolygons.Contains(Description->GetTrianglePolygon(Face)) != bTarget ||
            (bInstalled && (Description->GetTrianglePolygonGroup(Face) == RibbonGroup) != bTarget))
        {
            return Fail(Mesh, TEXT("Ribbon selection does not match complete source polygons."));
        }
        for (FVertexInstanceID Corner : Description->GetTriangleVertexInstances(Face))
        {
            const FVector2f* Offset = Offsets.Find(Corner);
            if (bool(Offset) != bTarget ||
                (bInstalled && !UVs.Get(Corner, UVChannel).Equals(Offset ? *Offset : FVector2f::ZeroVector, KINDA_SMALL_NUMBER)))
            {
                return Fail(Mesh, TEXT("Shared non-ribbon corner or mismatched existing ribbon UV."));
            }
        }
    }
    if (bInstalled) return true;
    const int32 SourceTriangles = Description->Triangles().Num();
    Mesh->Modify();
    UVs.SetNumChannels(UVChannel + 1);
    for (const auto& Entry : Offsets) UVs.Set(Entry.Key, UVChannel, Entry.Value);
    RibbonGroup = Description->CreatePolygonGroup();
    Names[RibbonGroup] = RibbonSlot;
    for (FPolygonID Polygon : RibbonPolygons) Description->SetPolygonPolygonGroup(Polygon, RibbonGroup);
    Mesh->GetStaticMaterials().Emplace(Material, RibbonSlot, RibbonSlot);
    UStaticMesh::FCommitMeshDescriptionParams Params;
    Params.bUseHashAsGuid = true;
    Mesh->CommitMeshDescription(0, Params);
    Mesh->PostEditChange();
    UE_LOG(LogTemp, Display, TEXT("GHS road markings [%s]: %d of %d triangles, UV%d."),
           *Mesh->GetName(), Found.Num(), SourceTriangles, UVChannel);
    return true;
}
#endif
