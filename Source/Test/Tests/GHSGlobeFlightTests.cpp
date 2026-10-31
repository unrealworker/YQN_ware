#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSGlobeFlight.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GHSAutomationTestFlags.h"

namespace GHSGlobeFlightTests
{
constexpr auto Flags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;
const FVector Center(0,0,300000);
constexpr float Radius=10000;

FGHSCameraReplayPose PoseAt(FVector Eye,FRotator Rotation=FRotator(-27,71,0))
{
    FGHSCameraReplayPose Pose{};
    Pose.Distance=50000;Pose.Rotation=Rotation;
    Pose.SocketOffset=FVector(0,4500,-2200);Pose.TargetOffset=FVector(350,-170,90);
    Pose.Pivot=Eye-Pose.TargetOffset-Rotation.RotateVector(Pose.SocketOffset-FVector(Pose.Distance,0,0));
    Pose.FocusTarget=Center;Pose.FramingRatio=Pose.SocketOffset/Pose.Distance;
    Pose.ObjectPivot=true;Pose.UseFraming=true;Pose.OverviewFraming=false;Pose.GroundPanRecovery=false;
    Pose.RecoveryMinimum=Pose.RecoveryMaximum=FVector::ZeroVector;
    return Pose;
}
bool Finite(FVector V){return FMath::IsFinite(V.X)&&FMath::IsFinite(V.Y)&&FMath::IsFinite(V.Z);}
bool SamePose(const FGHSCameraReplayPose& A,const FGHSCameraReplayPose& B)
{
    return A.Pivot.Equals(B.Pivot,.0001)&&A.SocketOffset.Equals(B.SocketOffset,.0001)
        &&A.TargetOffset.Equals(B.TargetOffset,.0001)&&A.FocusTarget.Equals(B.FocusTarget,.0001)
        &&A.FramingRatio.Equals(B.FramingRatio,.0001)&&A.Rotation.Equals(B.Rotation,.0001)
        &&FMath::IsNearlyEqual(A.Distance,B.Distance,.0001f)&&A.ObjectPivot==B.ObjectPivot
        &&A.UseFraming==B.UseFraming&&A.OverviewFraming==B.OverviewFraming
        &&A.GroundPanRecovery==B.GroundPanRecovery&&A.RecoveryMinimum.Equals(B.RecoveryMinimum,.0001)
        &&A.RecoveryMaximum.Equals(B.RecoveryMaximum,.0001);
}
struct FCameraFixture
{
    UWorld* World=nullptr;
    AGHSWarehouseCameraPawn* Camera=nullptr;
    FCameraFixture()
    {
        World=UWorld::CreateWorld(EWorldType::Game,false);
        if(!World||!GEngine)return;
        GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
        World->InitializeActorsForPlay(FURL());
        Camera=World->SpawnActor<AGHSWarehouseCameraPawn>();
    }
    ~FCameraFixture()
    {
        if(!World)return;
        if(GEngine)GEngine->DestroyWorldContext(World);
        World->DestroyWorld(false);
    }
    void Tick(float Dt)
    {
        Camera->LastDeltaTime=Dt;Camera->Tick(Dt);
        Camera->SpringArmComponent->TickComponent(Dt,LEVELTICK_All,nullptr);
    }
};
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeFlightCurrentPose,"GHS.Globe.Flight.CurrentLaggedPoseContinuity",GHSGlobeFlightTests::Flags)
bool FGHSGlobeFlightCurrentPose::RunTest(const FString&)
{
    using namespace GHSGlobeFlightTests;
    FCameraFixture F;if(!TestNotNull(TEXT("Camera fixture"),F.Camera))return false;
    F.Camera->WarehouseCamera->FieldOfView=20;F.Camera->MinimumZoom=11200;F.Camera->MaximumZoom=200000;
    F.Camera->MinimumPitch=-80;F.Camera->MaximumPitch=80;F.Camera->SetObjectOrbitNavigationEnabled(true);
    F.Camera->FocusOnTarget(Center,90000,FRotator(-32,-96,0),FVector2D(1672,941),FVector2D(650,480),0);
    F.Camera->OrbitPixels(FVector2D(180,-60));F.Camera->ZoomSteps(3);F.Tick(1.f/60.f);
    const auto Start=F.Camera->CaptureReplayPose();
    const FVector ActualEye=F.Camera->WarehouseCamera->GetComponentLocation();
    TestTrue(TEXT("Fixture has unfinished zoom lag"),FMath::Abs(Start.Distance-F.Camera->DesiredZoom)>100);
    TestFalse(TEXT("Fixture has unfinished rotation lag"),Start.Rotation.Equals(F.Camera->DesiredRotation,.1));
    TestFalse(TEXT("Fixture uses off-axis framing"),Start.SocketOffset.IsNearlyZero());
    TestTrue(TEXT("Flight eye reconstruction matches the rendered CameraComponent"),FGHSGlobeFlight::Eye(Start).Equals(ActualEye,.01));
    FGHSGlobeFlight Flight;Flight.Begin(Start,Center,Radius,Center-FVector::ForwardVector*Radius);
    TestTrue(TEXT("t=0 preserves every captured pose field"),SamePose(Start,Flight.Sample(0)));
    F.Camera->RestoreReplayPose(Flight.Sample(0));F.Tick(1.f/60.f);
    TestTrue(TEXT("Applying t=0 freezes the current view instead of the pending lag destination"),F.Camera->WarehouseCamera->GetComponentLocation().Equals(ActualEye,.01));
    const auto Tiny=Flight.Sample(.00001f);
    TestTrue(TEXT("Tiny positive time has no position jump"),FGHSGlobeFlight::Eye(Tiny).Equals(ActualEye,.01));
    TestTrue(TEXT("Tiny positive time has no orientation jump"),Tiny.Rotation.Equals(Start.Rotation,.001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeFlightSurfaceClearance,"GHS.Globe.Flight.BacksideDatelineAndPoles",GHSGlobeFlightTests::Flags)
bool FGHSGlobeFlightSurfaceClearance::RunTest(const FString&)
{
    using namespace GHSGlobeFlightTests;
    struct FRoute{FVector From,To;};
    const FRoute Routes[]={
        {FVector::ForwardVector,-FVector::ForwardVector},
        {FRotator(0,179,0).Vector(),FRotator(0,-179,0).Vector()},
        {FVector::UpVector,-FVector::UpVector},
        {FVector::ForwardVector,FVector::UpVector},
        {FVector(1,2,3).GetSafeNormal(),FVector(-2,3,-1).GetSafeNormal()},
        {FVector::ForwardVector,FVector::ForwardVector}
    };
    for(int32 RouteIndex=0;RouteIndex<UE_ARRAY_COUNT(Routes);++RouteIndex)
    {
        const auto& Route=Routes[RouteIndex];
        FGHSGlobeFlight Flight;Flight.Begin(PoseAt(Center+Route.From*Radius*8),Center,Radius,Center+Route.To*Radius);
        for(int32 I=0;I<=100;++I)
        {
            const auto Pose=Flight.Sample(float(I)/100.f);const FVector Eye=FGHSGlobeFlight::Eye(Pose);
            const FString Label=FString::Printf(TEXT("Route %d sample %d"),RouteIndex,I);
            TestTrue(Label+TEXT(" has a finite eye, pivot and orientation"),Finite(Eye)&&Finite(Pose.Pivot)&&Finite(Pose.Rotation.Euler())&&FMath::IsFinite(Pose.Distance));
            TestTrue(Label+TEXT(" keeps the actual eye above the Earth surface"),FVector::Dist(Eye,Center)>Radius);
        }
        const auto End=Flight.Sample(1);const FVector EndOffset=FGHSGlobeFlight::Eye(End)-Center;
        TestTrue(TEXT("Arrival remains at 1.04 Earth radii"),FMath::IsNearlyEqual(EndOffset.Size(),double(Radius)*1.04,.02));
        TestTrue(TEXT("Arrival lies on the destination outward normal"),EndOffset.GetSafeNormal().Equals(Route.To,.00001));
        TestTrue(TEXT("Arrival looks directly at the destination surface"),End.Rotation.Vector().Equals(-Route.To,.00001));
        TestTrue(TEXT("Arrival removes old framing and target offsets"),End.SocketOffset.IsNearlyZero(.001)&&End.TargetOffset.IsNearlyZero(.001));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeFlightGreatCircle,"GHS.Globe.Flight.ArcDoesNotCutThroughEarth",GHSGlobeFlightTests::Flags)
bool FGHSGlobeFlightGreatCircle::RunTest(const FString&)
{
    using namespace GHSGlobeFlightTests;
    const auto Start=PoseAt(Center+FVector::ForwardVector*Radius*8);
    FGHSGlobeFlight Flight;Flight.Begin(Start,Center,Radius,Center-FVector::ForwardVector*Radius);
    const FVector BeginEye=FGHSGlobeFlight::Eye(Start),EndEye=FGHSGlobeFlight::Eye(Flight.Sample(1));
    TestTrue(TEXT("The direct chord for this route would penetrate the Earth"),FVector::Dist(FMath::Lerp(BeginEye,EndEye,.9),Center)<Radius);
    const FVector Mid=FGHSGlobeFlight::Eye(Flight.Sample(.5f))-Center;
    TestTrue(TEXT("Antipodal midpoint goes around the globe instead of along the direct chord"),FVector(0,Mid.Y,Mid.Z).Size()>Radius);
    TestTrue(TEXT("Halfway angular travel reaches the great-circle quarter turn"),FMath::Abs(Mid.GetSafeNormal().X)<.00001);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeFlightDeterminism,"GHS.Globe.Flight.FrameRateIndependent",GHSGlobeFlightTests::Flags)
bool FGHSGlobeFlightDeterminism::RunTest(const FString&)
{
    using namespace GHSGlobeFlightTests;
    const auto Start=PoseAt(Center+FVector(1,2,3).GetSafeNormal()*Radius*8);
    const FVector Destination=Center+FVector(-2,-1,1).GetSafeNormal()*Radius;
    FGHSGlobeFlight Reference;Reference.Begin(Start,Center,Radius,Destination);
    for(const int32 Fps:{24,30,60,120})
    {
        FGHSGlobeFlight Flight;Flight.Begin(Start,Center,Radius,Destination);
        float Elapsed=0;FGHSCameraReplayPose Current{};
        for(int32 Frame=0;Frame<Fps;++Frame){Elapsed+=1.f/Fps;Current=Flight.Sample(Elapsed/FGHSGlobeFlight::Duration);}
        const auto Expected=Reference.Sample(1.f/FGHSGlobeFlight::Duration);
        TestTrue(FString::Printf(TEXT("%d FPS reaches the same eye after one second"),Fps),FGHSGlobeFlight::Eye(Current).Equals(FGHSGlobeFlight::Eye(Expected),.2));
        TestTrue(TEXT("Frame rate does not change flight orientation"),Current.Rotation.Equals(Expected.Rotation,.001));
        Flight.Sample(.9f);Flight.Sample(.1f);
        TestTrue(TEXT("Out-of-order evaluations cannot mutate the path"),SamePose(Flight.Sample(.5f),Reference.Sample(.5f)));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSGlobeFlightNearSurface,"GHS.Globe.Flight.NearSurfaceStartContinuity",GHSGlobeFlightTests::Flags)
bool FGHSGlobeFlightNearSurface::RunTest(const FString&)
{
    using namespace GHSGlobeFlightTests;
    const auto Start=PoseAt(Center+FVector::ForwardVector*(Radius+10));
    FGHSGlobeFlight Flight;Flight.Begin(Start,Center,Radius,Center-FVector::ForwardVector*Radius);
    TestTrue(TEXT("A valid near-surface pose is preserved at t=0"),SamePose(Start,Flight.Sample(0)));
    const auto Tiny=Flight.Sample(.00001f);
    TestTrue(TEXT("A valid eye below the arrival altitude is not snapped out to it"),FGHSGlobeFlight::Eye(Tiny).Equals(FGHSGlobeFlight::Eye(Start),.01));
    TestTrue(TEXT("The current level-horizon orientation is continuous"),Tiny.Rotation.Equals(Start.Rotation,.001));
    for(int32 I=0;I<=100;++I)
        TestTrue(TEXT("Near-surface start remains exterior throughout its approach"),FVector::Dist(FGHSGlobeFlight::Eye(Flight.Sample(float(I)/100)),Center)>Radius);
    return true;
}
#endif
