#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSGlobeCountryLabels.h"
#include "../GHSWarehouseRegistry.h"
#include "Components/DecalComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include "GHSAutomationTestFlags.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeCountrySurfaceLabelsTest, "GHS.Globe.CountrySurfaceLabels", GHSAutomationTests::ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGHSGlobeCountrySurfaceLabelsTest::RunTest(const FString&)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Country label test world"), World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World); World->DestroyWorld(false); };
    World->InitializeActorsForPlay(FURL());
    auto* Earth = World->SpawnActor<AActor>();
    auto* Root = NewObject<USceneComponent>(Earth);
    Earth->SetRootComponent(Root);
    Root->RegisterComponent();
    Earth->SetActorLocation(FVector(0, 0, 300000));
    Earth->SetActorScale3D(FVector(100));
    auto* Labels = World->SpawnActor<AGHSGlobeCountryLabels>();
    Labels->Initialize(Earth, 10000.f);
    TArray<UDecalComponent*> Decals;
    Labels->GetComponents(Decals);
    if (!TestEqual(TEXT("All configured country names have surface decals"), Decals.Num(), 14)) return false;
    UDecalComponent* China = nullptr;
    for (auto* Label : Decals) if (Label->ComponentHasTag(TEXT("Country:中国"))) China = Label;
    if (!TestNotNull(TEXT("Country identity remains inspectable"), China)) return false;
    TestNotNull(TEXT("Country atlas material available"), China->GetDecalMaterial());
    const FVector Radial = GHSGlobe::ToSphere(35, 103, 1.);
    const double Lat = FMath::DegreesToRadians(35.), Lon = FMath::DegreesToRadians(103.);
    const FVector North(-FMath::Sin(Lat)*FMath::Cos(Lon), FMath::Sin(Lat)*FMath::Sin(Lon), FMath::Cos(Lat));
    const FVector East(-FMath::Sin(Lon), -FMath::Cos(Lon), 0);
    const FTransform Local = China->GetRelativeTransform();
    for (const FRotator Rotation : {FRotator::ZeroRotator, FRotator(30, 140, -12), FRotator(-65, -105, 25)})
    {
        Earth->SetActorRotation(Rotation);
        const FQuat Q = Rotation.Quaternion();
        TestTrue(TEXT("Country location remains on the geographic radial"), China->GetComponentLocation().Equals(Earth->GetActorLocation()+Q.RotateVector(Radial*10150.), .001));
        TestTrue(TEXT("Country projection stays inward as Earth tilts"), China->GetForwardVector().Equals(Q.RotateVector(-Radial), .00001));
        TestTrue(TEXT("Atlas V points south on globe"), China->GetRightVector().Equals(Q.RotateVector(-North), .00001));
        TestTrue(TEXT("Atlas U points east on globe without mirrored glyphs"), China->GetUpVector().Equals(Q.RotateVector(East), .00001));
        TestTrue(TEXT("No camera-facing rotation replaces the tangent transform"), China->GetRelativeTransform().Equals(Local));
        TestTrue(TEXT("Earth import scale does not inflate country typography"), China->GetComponentScale().Equals(FVector::OneVector));
    }
    Labels->Initialize(Earth, 10000.f);
    Labels->GetComponents(Decals);
    TestEqual(TEXT("Reinitialization removes old country label components"), Decals.Num(), 14);
    Labels->SetActorHiddenInGame(true);
    TestTrue(TEXT("Country labels follow global-stage visibility"), Labels->IsHidden());
    return true;
}
#endif
