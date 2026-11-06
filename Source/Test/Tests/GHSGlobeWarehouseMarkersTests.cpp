#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSGlobeWarehouseMarkers.h"
#include "Components/DecalComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include "GHSAutomationTestFlags.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeSurfaceMarkersTest, "GHS.Globe.SurfaceMarkers", GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSGlobeSurfaceMarkersTest::RunTest(const FString&)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Marker test world"), World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World); World->DestroyWorld(false); };
    World->InitializeActorsForPlay(FURL());
    auto* Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/GlobeNavigation/SM_Earth.SM_Earth"));
    if (!TestNotNull(TEXT("Earth surface asset available"), Mesh)) return false;
    TestTrue(TEXT("Shipping keeps CPU geometry for geographic anchors"), bool(Mesh->bAllowCPUAccess));
    auto* Earth = World->SpawnActor<AActor>();
    auto* EarthRoot = NewObject<UStaticMeshComponent>(Earth);
    Earth->SetRootComponent(EarthRoot);
    EarthRoot->SetMobility(EComponentMobility::Movable);
    EarthRoot->SetStaticMesh(Mesh);
    EarthRoot->RegisterComponent();
    Earth->SetActorLocation(FVector(0, 0, 300000));
    Earth->SetActorRotation(FRotator(0, 37, 0));
    Earth->SetActorScale3D(FVector(100));
    auto* Markers = World->SpawnActor<AGHSGlobeWarehouseMarkers>();
    FGHSGlobeWarehouse MPR, GHS;
    MPR.Id = TEXT("mpr-nj"); MPR.Latitude = 40.568197; MPR.Longitude = -74.242175;
    GHS.Id = TEXT("ghs-ca"); GHS.Latitude = 34.190629582941; GHS.Longitude = -117.428430792609;
    Markers->Initialize(Earth, 10000.f, {MPR, GHS});
    TestEqual(TEXT("One exact surface anchor per warehouse"), Markers->GetAnchorCount(), 2);
    TArray<UDecalComponent*> Decals;
    Markers->GetComponents(Decals);
    TestEqual(TEXT("Native pixel overlay has no duplicate world-size decal"), Decals.Num(), 0);
    for (const auto& Warehouse : {MPR, GHS})
    {
        FVector Point;
        if (!TestTrue(TEXT("Warehouse has a surface intersection"), Markers->GetWorldAnchor(Warehouse.Id, Point))) return false;
        const FVector Local = EarthRoot->GetComponentTransform().InverseTransformPosition(Point);
        const FVector Direction = GHSGlobe::ToSphere(Warehouse.Latitude, Warehouse.Longitude, 1.);
        TestTrue(TEXT("Surface anchor stays on its geographic ray"), Local.GetSafeNormal().Equals(Direction, 1.e-6));
        TestTrue(TEXT("Anchor uses Earth relief, in local centimeter mesh bounds"), Local.Length() > 99.5 && Local.Length() < 105.);
        TestFalse(TEXT("Anchor is not the previous arbitrary elevated projector"), FMath::IsNearlyEqual(Local.Length(), 101.5, .0001));
        for (const FRotator Rotation : {FRotator(0, -90, 0), FRotator(45, 175, 15), FRotator(-70, -160, -20)})
        {
            Earth->SetActorRotation(Rotation);
            Earth->SetActorScale3D(FVector(125));
            Markers->GetWorldAnchor(Warehouse.Id, Point);
            const FVector Expected = EarthRoot->GetComponentTransform().TransformPosition(Local);
            TestTrue(TEXT("Anchor follows current Earth rotation and scale without frame lag"), Point.Equals(Expected, 1.e-6));
        }
    }
    FVector Unchanged(42, 43, 44);
    TestFalse(TEXT("Unknown warehouse cannot produce a fake point"), Markers->GetWorldAnchor(TEXT("missing"), Unchanged));
    TestTrue(TEXT("Missing anchor leaves the caller output alone"), Unchanged.Equals(FVector(42, 43, 44)));
    Markers->Initialize(Earth, 10000.f, {MPR});
    TestEqual(TEXT("Reinitialization clears previous warehouse anchors"), Markers->GetAnchorCount(), 1);
    TestFalse(TEXT("Removed warehouse cannot retain a stale point"), Markers->GetWorldAnchor(GHS.Id, Unchanged));
    return true;
}
#endif
