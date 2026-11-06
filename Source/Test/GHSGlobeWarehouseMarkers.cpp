#include "GHSGlobeWarehouseMarkers.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"

namespace
{
struct FSurfaceTriangle
{
    FVector A, B, C, Center;
    double RadiusSquared;
};

bool FindSurface(const TArray<FSurfaceTriangle>& Triangles, const FVector& Direction, double RayLength, FVector& OutPosition)
{
    double FarthestHit = 0;
    for (const auto& Triangle : Triangles)
    {
        // Reject triangles whose bounds cannot intersect this radial ray before
        // doing barycentric work. This also skips the opposite hemisphere.
        const double Along = FVector::DotProduct(Triangle.Center, Direction);
        if (Along <= 0 || Triangle.Center.SizeSquared() - Along * Along > Triangle.RadiusSquared + 1.e-6)
            continue;
        FVector Hit, Normal;
        if (FMath::SegmentTriangleIntersection(FVector::ZeroVector, Direction * RayLength,
            Triangle.A, Triangle.B, Triangle.C, Hit, Normal))
        {
            const double Distance = FVector::DotProduct(Hit, Direction);
            if (Distance > FarthestHit) { FarthestHit = Distance; OutPosition = Hit; }
        }
    }
    return FarthestHit > 0;
}
}

AGHSGlobeWarehouseMarkers::AGHSGlobeWarehouseMarkers()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("SurfaceMarkerRoot")));
    RootComponent->SetMobility(EComponentMobility::Movable);
    Tags.Add(TEXT("GHS_GlobeWarehouseMarkers"));
}

void AGHSGlobeWarehouseMarkers::Initialize(AActor* GlobeRoot, float GlobeRadius, const TArray<FGHSGlobeWarehouse>& Warehouses)
{
    LocalAnchors.Reset();
    EarthMesh.Reset();
    if (!IsValid(GlobeRoot) || !GlobeRoot->GetRootComponent() || !FMath::IsFinite(GlobeRadius) || GlobeRadius <= 0.f)
        return;
    AttachToActor(GlobeRoot, FAttachmentTransformRules::SnapToTargetIncludingScale);
    auto* Component = GlobeRoot->FindComponentByClass<UStaticMeshComponent>();
    UStaticMesh* Mesh = Component ? Component->GetStaticMesh() : nullptr;
    const auto* RenderData = Mesh ? Mesh->GetRenderData() : nullptr;
    if (!Mesh || !Mesh->bAllowCPUAccess || !RenderData || RenderData->LODResources.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("GHS globe surface anchors require an Earth mesh with Allow CPU Access enabled"));
        return;
    }
    const auto& LOD = RenderData->LODResources[0];
    const auto& Positions = LOD.VertexBuffers.PositionVertexBuffer;
    if (!Positions.GetVertexData() || LOD.IndexBuffer.GetIndexDataSize() == 0)
    {
        UE_LOG(LogTemp, Error, TEXT("GHS globe surface anchor CPU geometry is unavailable"));
        return;
    }
    const auto Indices = LOD.IndexBuffer.GetArrayView();
    TArray<FSurfaceTriangle> Triangles;
    Triangles.Reserve(Indices.Num() / 3);
    for (int32 I = 0; I + 2 < Indices.Num(); I += 3)
    {
        const FVector A(Positions.VertexPosition(Indices[I]));
        const FVector B(Positions.VertexPosition(Indices[I + 1]));
        const FVector C(Positions.VertexPosition(Indices[I + 2]));
        const FVector Center = (A + B + C) / 3.;
        Triangles.Add({A, B, C, Center, FMath::Max3((A - Center).SizeSquared(), (B - Center).SizeSquared(), (C - Center).SizeSquared())});
    }
    EarthMesh = Component;
    const double RayLength = Mesh->GetBounds().SphereRadius * 2.;
    for (const auto& Warehouse : Warehouses)
    {
        if (LocalAnchors.Contains(Warehouse.Id) || !GHSGlobe::ValidCoordinates(Warehouse.Latitude, Warehouse.Longitude))
            continue;
        FVector Local;
        // Exact imported-mesh coordinates include relief. An invented radius
        // offset would visually drift away from the map at oblique views.
        if (FindSurface(Triangles, GHSGlobe::ToSphere(Warehouse.Latitude, Warehouse.Longitude, 1.), RayLength, Local))
            LocalAnchors.Add(Warehouse.Id, Local);
        else
            UE_LOG(LogTemp, Error, TEXT("GHS globe mesh has no surface for warehouse %s"), *Warehouse.Id);
    }
}

bool AGHSGlobeWarehouseMarkers::GetWorldAnchor(const FString& WarehouseId, FVector& OutPosition) const
{
    const FVector* Local = LocalAnchors.Find(WarehouseId);
    if (!Local || !EarthMesh.IsValid()) return false;
    OutPosition = EarthMesh->GetComponentTransform().TransformPosition(*Local);
    return true;
}
