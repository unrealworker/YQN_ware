#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSOrderReplaySession.h"
#include "Misc/AutomationTest.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/CameraComponent.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayClockTest,"GHS.Replay.Transport",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayClockTest::RunTest(const FString&)
{
    FGHSReplayClock C;
    TestFalse(TEXT("59m59s rejected"),C.Start(3599));
    TestTrue(TEXT("one hour accepted"),C.Start(3600));
    C.Advance(2);TestEqual(TEXT("normal clock"),C.Time,2.);
    C.Playing=false;C.Advance(50);TestEqual(TEXT("pause freezes time"),C.Time,2.);
    C.Seek(3500);TestFalse(TEXT("seek preserves pause"),C.Playing);
    C.SetRate(64);C.Playing=true;C.Advance(10);
    TestEqual(TEXT("exact interval end"),C.Time,3600.);TestFalse(TEXT("stops at end"),C.Playing);
    C.Seek(230);TestEqual(TEXT("rewind is direct"),C.Time,230.);
    C.Seek(std::numeric_limits<double>::infinity());TestEqual(TEXT("reject nonfinite seek"),C.Time,230.);
    C.SetRate(3);TestEqual(TEXT("unsupported speed does not change rate"),C.Rate,64.);
    C.SetRate(1);C.Playing=true;C.Advance(-1);TestEqual(TEXT("negative delta ignored"),C.Time,230.);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayExitTest,"GHS.Replay.ExitGuard",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayExitTest::RunTest(const FString&)
{
    FGHSReplayClock C;C.Start(3600);C.Seek(230);C.SetRate(8);
    FGHSReplayExitGuard G;
    TestTrue(TEXT("first pending request accepted"),G.Request(TEXT("navigate inventory"),C));
    TestFalse(TEXT("duplicate does not replace original operation"),G.Request(TEXT("focus wrong"),C));
    TestFalse(TEXT("confirmation freezes playback"),C.Playing);C.Advance(30);
    TestEqual(TEXT("time held while deciding"),C.Time,230.);
    G.Cancel(C);TestTrue(TEXT("cancel restores playing"),C.Playing);
    TestEqual(TEXT("cancel preserves rate"),C.Rate,8.);
    C.Playing=false;G.Request(TEXT("focus device"),C);G.Cancel(C);
    TestFalse(TEXT("cancel preserves paused state"),C.Playing);
    G.Request(TEXT("focus device"),C);
    TestEqual(TEXT("confirm executes original once"),G.Consume(),FString(TEXT("focus device")));
    TestTrue(TEXT("duplicate confirm has no operation"),G.Consume().IsEmpty());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayCameraRestoreTest,"GHS.Replay.CameraRestoration",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayCameraRestoreTest::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("transient world"),World)) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);World->InitializeActorsForPlay(FURL());
    auto* Camera=World->SpawnActor<AGHSWarehouseCameraPawn>();
    if(TestNotNull(TEXT("camera"),Camera))
    {
        Camera->FocusOnTarget(FVector(1234,4567,180),4200,FRotator(-41,-120,0),FVector2D(1920,1080),FVector2D(650,550),0);
        const auto Before=Camera->CaptureReplayPose();
        Camera->FocusOnTarget(FVector(-2300,1100,90),1800,FRotator(-38,20,0),FVector2D(1920,1080),FVector2D(700,450),0);
        Camera->RestoreReplayPose(Before);const auto After=Camera->CaptureReplayPose();
        TestTrue(TEXT("exact rendered pivot restored"),Before.Pivot.Equals(After.Pivot));
        TestTrue(TEXT("exact rendered azimuth restored"),Before.Rotation.Equals(After.Rotation));
        TestEqual(TEXT("original distance restored"),Before.Distance,After.Distance);
        TestTrue(TEXT("framing offsets restored"),Before.SocketOffset.Equals(After.SocketOffset) && Before.TargetOffset.Equals(After.TargetOffset));
        TestEqual(TEXT("object pivot preserved"),Before.ObjectPivot,After.ObjectPivot);
        Camera->FollowReplayTarget(Before.Pivot+FVector(100,200,0),.1f);
        TestTrue(TEXT("follow moves smoothly toward device"),Camera->GetActorLocation().Equals(Before.Pivot+FVector(50,100,0),.01));
        TestTrue(TEXT("follow keeps the chosen viewing angle"),Camera->GetActorRotation().Equals(Before.Rotation));
        TestTrue(TEXT("follow does not reset user's zoom"),FMath::IsNearlyEqual(Camera->SpringArmComponent->TargetArmLength,Before.Distance));

        Camera->FocusOnTarget(FVector(Camera->OverviewCenter.X+Camera->MaximumPan.X+15000,0,400),4200,FRotator(-41,0,0),FVector2D(1920,1080),FVector2D(650,550),0);
        Camera->PrepareForGroundPan();
        const auto GroundBefore=Camera->CaptureReplayPose();
        TestFalse(TEXT("exterior device view converted to ground navigation"),GroundBefore.ObjectPivot);
        TestTrue(TEXT("fixture is beyond ordinary ground bound"),GroundBefore.Pivot.X>Camera->OverviewCenter.X+Camera->MaximumPan.X);
        Camera->FocusOnTarget(FVector(0,0,100),1800,FRotator(-38,0,0),FVector2D(1920,1080),FVector2D(700,450),0);
        Camera->RestoreReplayPose(GroundBefore);
        for(int32 I=0;I<12;++I) Camera->Tick(1.f/60.f);
        TestTrue(TEXT("restored recovery mode does not snap exterior pivot on following ticks"),Camera->GetActorLocation().Equals(GroundBefore.Pivot,.01));
    }
    GEngine->DestroyWorldContext(World);World->DestroyWorld(false);return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayFollowNavigationTest,"GHS.Replay.FollowNavigation",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayFollowNavigationTest::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("transient follow world"),World)) return false;
    GEngine->CreateNewWorldContext(World->WorldType).SetCurrentWorld(World);World->InitializeActorsForPlay(FURL());
    auto* Camera=World->SpawnActor<AGHSWarehouseCameraPawn>();
    Camera->FocusOnTarget(FVector(1000,2000,150),1800,FRotator(-62,-65,0),FVector2D(1920,1080),FVector2D(700,490),0);
    const auto Original=Camera->CaptureReplayPose();
    Camera->FollowReplayTarget(Original.Pivot,.1f);
    Camera->OrbitPixels(FVector2D(140,-35));Camera->ZoomSteps(-2);
    const FRotator UserRotation=Camera->DesiredRotation;const float UserZoom=Camera->DesiredZoom;
    for(int32 I=0;I<120;++I)
    {
        Camera->FollowReplayTarget(FVector(1800,2500,150),1.f/60.f);
        Camera->Tick(1.f/60.f);
    }
    TestTrue(TEXT("moving device does not override user's orbit target"),Camera->DesiredRotation.Equals(UserRotation,.01));
    TestTrue(TEXT("orbit lag completes while following"),Camera->GetActorRotation().Equals(UserRotation,.05));
    TestEqual(TEXT("follow does not erase wheel zoom target"),Camera->DesiredZoom,UserZoom);
    TestTrue(TEXT("wheel zoom completes while following"),FMath::IsNearlyEqual(Camera->SpringArmComponent->TargetArmLength,UserZoom,.1f));
    TestTrue(TEXT("follow still tracks the moving device"),Camera->GetActorLocation().Equals(FVector(1800,2500,150),.1));
    const auto FollowPose=Camera->CaptureReplayPose();
    Camera->PanPixels(FVector2D(300,160),1920);Camera->PrepareForGroundPan();
    TestTrue(TEXT("both direct pan and ground conversion are blocked during follow"),Camera->DesiredLocation.Equals(FollowPose.Pivot) && Camera->UsesObjectPivot());
    TestTrue(TEXT("follow framing is retained"),Camera->SpringArmComponent->SocketOffset.Equals(FollowPose.SocketOffset));
    Camera->RestoreReplayPose(Original);Camera->PanPixels(FVector2D(100,0),1920);
    TestFalse(TEXT("restoring the original view releases the pan lock"),Camera->DesiredLocation.Equals(Original.Pivot));
    GEngine->DestroyWorldContext(World);World->DestroyWorld(false);return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayWorkAreaFramingTest,"GHS.Replay.WorkAreaFraming",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayWorkAreaFramingTest::RunTest(const FString&)
{
    // Actual floor cargo bounds plus its loading apron, never the truck's public-road route.
    const FBox Bounds(FVector(-7104,-5647,0),FVector(20605,7539,450));
    const FRotator Rotation(-58,-90,0);const FRotationMatrix Basis(Rotation);
    for(const FVector2D Viewport:{FVector2D(1920,1080),FVector2D(1366,768)})
    {
        const FBox2D Scene(FVector2D(28,136),FVector2D(Viewport.X-492,Viewport.Y-216));
        const float Distance=AGHSWarehouseCameraPawn::CalculateFramingDistance(Bounds,Rotation,56,Viewport,Scene);
        TestTrue(TEXT("work-area view is closer than the former campus framing"),Distance>900 && Distance<53500*Viewport.X/(Scene.Max.X-Scene.Min.X));
        const double K=Viewport.X/(2*FMath::Tan(FMath::DegreesToRadians(28.)));
        const FVector2D Center=Scene.GetCenter();
        const FVector Offset(0,(Viewport.X*.5-Center.X)*Distance/K,(Center.Y-Viewport.Y*.5)*Distance/K);
        for(int32 I=0;I<8;++I)
        {
            const FVector Corner(I&1?Bounds.Max.X:Bounds.Min.X,I&2?Bounds.Max.Y:Bounds.Min.Y,I&4?Bounds.Max.Z:Bounds.Min.Z);
            FVector Local=Basis.GetTransposed().TransformVector(Corner-Bounds.GetCenter());Local.X+=Distance;Local-=Offset;
            const FVector2D Pixel(Viewport.X*.5+K*Local.Y/Local.X,Viewport.Y*.5-K*Local.Z/Local.X);
            TestTrue(TEXT("work-area corner avoids panel, header and timeline"),Pixel.X>=Scene.Min.X-.1 && Pixel.X<=Scene.Max.X+.1 && Pixel.Y>=Scene.Min.Y-.1 && Pixel.Y<=Scene.Max.Y+.1);
        }
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSReplayRoofRestoreTest,"GHS.Replay.RoofVisibilityRestoration",EAutomationTestFlags::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSReplayRoofRestoreTest::RunTest(const FString&)
{
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false);
    if(!TestNotNull(TEXT("transient roof world"),World) || !GEngine) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);World->InitializeActorsForPlay(FURL());
    auto* Roof=World->SpawnActor<AStaticMeshActor>();Roof->Tags.Add(TEXT("GHS_WarehouseRoof"));
    auto* Mesh=Roof->GetStaticMeshComponent();Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
    auto* Facade=World->SpawnActor<AStaticMeshActor>();Facade->Tags.Add(TEXT("GHS_OfficeFacade"));Facade->GetStaticMeshComponent()->SetStaticMesh(Mesh->GetStaticMesh());
    auto* Owner=World->SpawnActor<AActor>();auto* Component=NewObject<UGHSWarehouseRoofComponent>(Owner);
    Owner->AddInstanceComponent(Component);Component->RegisterComponent();Component->InitializeRoof();
    Roof->SetActorHiddenInGame(true);Mesh->SetVisibility(false);Mesh->SetHiddenInGame(true);Facade->SetActorHiddenInGame(true);
    const auto Hidden=Component->CaptureReplayState();
    Component->OpenRoof(true);
    TestTrue(TEXT("manual facade hide survives opening for replay"),Facade->IsHidden());
    Component->TickComponent(.6f,LEVELTICK_All,nullptr);Component->RestoreReplayState(Hidden,true);
    TestTrue(TEXT("closed roof phase restored"),Component->IsRoofClosed());
    TestTrue(TEXT("manual roof actor hide restored"),Roof->IsHidden());
    TestFalse(TEXT("manual roof component visibility restored"),Mesh->IsVisible());
    TestTrue(TEXT("manual roof component hidden-in-game restored"),Mesh->bHiddenInGame);
    TestTrue(TEXT("manual facade hide restored"),Facade->IsHidden());
    Component->SetBuildingVisible(true);TestTrue(TEXT("subsequent shell refresh preserves manual override"),Facade->IsHidden());

    Roof->SetActorHiddenInGame(false);Mesh->SetVisibility(true);Mesh->SetHiddenInGame(false);Facade->SetActorHiddenInGame(false);
    Component->OpenRoof();Component->TickComponent(.2f,LEVELTICK_All,nullptr);
    const auto Transition=Component->CaptureReplayState();const float Phase=Component->GetTransitionPhase();
    Component->OpenRoof(true);Component->TickComponent(.6f,LEVELTICK_All,nullptr);Component->RestoreReplayState(Transition,true);
    TestTrue(TEXT("partly open roof resumes same transition"),Component->IsOpening());
    TestEqual(TEXT("partly open roof resumes exact aperture"),Component->GetTransitionPhase(),Phase);
    Component->TickComponent(.8f,LEVELTICK_All,nullptr);TestTrue(TEXT("restored transition can complete"),Component->IsInteriorAvailable());

    Component->SetBuildingVisible(false);const auto LayerOff=Component->CaptureReplayState();
    Component->SetBuildingVisible(true);Component->RestoreReplayState(LayerOff,false);
    TestFalse(TEXT("building layer remains off"),Component->IsBuildingVisible());
    TestTrue(TEXT("layer-hidden facade remains hidden"),Facade->IsHidden());
    GEngine->DestroyWorldContext(World);World->DestroyWorld(false);return true;
}
#endif
