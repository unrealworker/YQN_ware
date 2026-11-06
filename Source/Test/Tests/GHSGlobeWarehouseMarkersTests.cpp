#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSGlobeWarehouseMarkers.h"
#include "Components/DecalComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/Engine.h"
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
    auto* Earth = World->SpawnActor<AActor>();
    auto* EarthRoot = NewObject<USceneComponent>(Earth);
    Earth->SetRootComponent(EarthRoot);
    EarthRoot->RegisterComponent();
    Earth->SetActorLocation(FVector(0, 0, 300000));
    Earth->SetActorRotation(FRotator(0, 37, 0));
    Earth->SetActorScale3D(FVector(100));
    auto* Markers = World->SpawnActor<AGHSGlobeWarehouseMarkers>();
    FGHSGlobeWarehouse Warehouse;
    Warehouse.Id = TEXT("mpr-nj");
    Warehouse.Latitude = 40.568197;
    Warehouse.Longitude = -74.242175;
    Markers->Initialize(Earth, 10000.f, {Warehouse});
    TArray<UDecalComponent*> Decals;
    Markers->GetComponents(Decals);
    if (!TestEqual(TEXT("One native decal for one warehouse"), Decals.Num(), 1)) return false;
    auto* Decal = Decals[0];
    TestNotNull(TEXT("Cooked surface glow material is available"), Decal->GetDecalMaterial());
    TestTrue(TEXT("Scaled Earth does not inflate marker footprint"), Decal->GetComponentScale().Equals(FVector::OneVector));
    const FVector Direction = GHSGlobe::ToSphere(Warehouse.Latitude, Warehouse.Longitude, 1.);
    const FTransform Local = Decal->GetRelativeTransform();
    for (const FRotator Rotation : {FRotator(0, -90, 0), FRotator(45, 175, 15), FRotator(-70, -160, -20)})
    {
        Earth->SetActorRotation(Rotation);
        const FVector Expected = Earth->GetActorLocation() + Rotation.RotateVector(Direction * 10150.);
        TestTrue(TEXT("Geographic projector rotates with Earth in the same transform update"), Decal->GetComponentLocation().Equals(Expected, .001));
        TestTrue(TEXT("Projection direction remains radial and inward"), Decal->GetForwardVector().Equals(-Rotation.RotateVector(Direction), .00001));
        TestTrue(TEXT("Rotation never changes the local anchor"), Decal->GetRelativeTransform().Equals(Local));
    }
    const FLinearColor Idle = Decal->DecalColor;
    Markers->SetSelectedWarehouse(Warehouse.Id);
    TestFalse(TEXT("Selection emphasizes the real surface marker"), Decal->DecalColor.Equals(Idle));
    TestTrue(TEXT("Selection does not move or resize the point"), Decal->GetRelativeTransform().Equals(Local) && Decal->DecalSize.Equals(FVector(400, 300, 300)));
    Markers->SetSelectedWarehouse(TEXT(""));
    TestTrue(TEXT("Clearing selection restores original glow"), Decal->DecalColor.Equals(Idle));
    Markers->SetActorHiddenInGame(true);
    TestTrue(TEXT("Globe stage hiding hides decal rendering"), Markers->IsHidden());
    Markers->Initialize(Earth, 10000.f, {Warehouse});
    Markers->GetComponents(Decals);
    TestEqual(TEXT("Reinitialization does not duplicate decals"), Decals.Num(), 1);
    return true;
}
#endif
