#include "GHSGlobeWarehouseMarkers.h"

#include "Components/DecalComponent.h"
#include "Components/SceneComponent.h"
#include "Materials/MaterialInterface.h"

namespace
{
const FLinearColor IdleColor(.015f, .26f, 1.f);
const FLinearColor SelectedColor(.025f, .65f, 1.f);
}

AGHSGlobeWarehouseMarkers::AGHSGlobeWarehouseMarkers()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("SurfaceMarkerRoot")));
    RootComponent->SetMobility(EComponentMobility::Movable);
    // SM_Earth has a 100x import scale. Only inherit its rotation and translation;
    // geographic radii and decal dimensions below are already in world units.
    RootComponent->SetAbsolute(false, false, true);
    Tags.Add(TEXT("GHS_GlobeWarehouseMarkers"));
}

void AGHSGlobeWarehouseMarkers::Initialize(AActor* GlobeRoot, float GlobeRadius, const TArray<FGHSGlobeWarehouse>& Warehouses)
{
    for (auto& Entry : Markers)
        if (Entry.Value) Entry.Value->DestroyComponent();
    Markers.Reset();
    SelectedId.Reset();
    if (!IsValid(GlobeRoot) || !GlobeRoot->GetRootComponent() || !FMath::IsFinite(GlobeRadius) || GlobeRadius <= 0.f)
        return;

    AttachToActor(GlobeRoot, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    SetActorRelativeLocation(FVector::ZeroVector);
    SetActorRelativeRotation(FRotator::ZeroRotator);
    SetActorScale3D(FVector::OneVector);

    auto* Material = LoadObject<UMaterialInterface>(nullptr,
        TEXT("/Game/GlobeNavigation/Materials/M_WarehouseSurfaceGlow.M_WarehouseSurfaceGlow"));
    if (!Material)
    {
        UE_LOG(LogTemp, Error, TEXT("GHS globe warehouse glow material is missing"));
        return;
    }
    for (const auto& Warehouse : Warehouses)
    {
        if (Markers.Contains(Warehouse.Id) || !GHSGlobe::ValidCoordinates(Warehouse.Latitude, Warehouse.Longitude))
            continue;
        const FVector Direction = GHSGlobe::ToSphere(Warehouse.Latitude, Warehouse.Longitude, 1.);
        auto* Marker = NewObject<UDecalComponent>(this, NAME_None, RF_Transient);
        AddInstanceComponent(Marker);
        Marker->SetupAttachment(RootComponent);
        Marker->ComponentTags.Add(TEXT("GHS_GlobeWarehouseGlow"));
        Marker->ComponentTags.Add(FName(*(TEXT("Warehouse:") + Warehouse.Id)));
        Marker->SetRelativeLocation(Direction * (GlobeRadius * 1.015));
        Marker->SetRelativeRotation((-Direction).Rotation());
        // This shallow volume spans the actual relief and all Earth LODs. The
        // emissive disk is shaded on the mesh surface, never at this box center.
        Marker->DecalSize = FVector(GlobeRadius * .04, GlobeRadius * .03, GlobeRadius * .03);
        Marker->SetFadeScreenSize(0.f);
        Marker->SetDecalMaterial(Material);
        Marker->SetDecalColor(IdleColor);
        Marker->RegisterComponent();
        Markers.Add(Warehouse.Id, Marker);
    }
}

void AGHSGlobeWarehouseMarkers::SetSelectedWarehouse(const FString& WarehouseId)
{
    if (SelectedId == WarehouseId) return;
    if (const auto* Previous = Markers.Find(SelectedId); Previous && *Previous)
        (*Previous)->SetDecalColor(IdleColor);
    SelectedId = WarehouseId;
    if (const auto* Selected = Markers.Find(SelectedId); Selected && *Selected)
        (*Selected)->SetDecalColor(SelectedColor);
}
