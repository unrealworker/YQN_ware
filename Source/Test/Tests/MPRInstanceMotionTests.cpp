#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRInstanceMotionHistory.h"
#include "GHSAutomationTestFlags.h"
#include "Components/InstancedStaticMeshComponent.h"

namespace
{
constexpr auto MPRInstanceMotionFlags=GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter;

UInstancedStaticMeshComponent* MakeMotionInstances(int32 Count)
{
    // Exercise the engine's real instance matrices without loading a map,
    // registering a scene proxy, starting physics, or changing the editor world.
    auto* Component=NewObject<UInstancedStaticMeshComponent>(GetTransientPackage(),NAME_None,RF_Transient);
    Component->SetMobility(EComponentMobility::Movable);
    Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Component->SetCanEverAffectNavigation(false);
    Component->SetWorldTransform(FTransform(FRotator(0,27,0),FVector(1200,-400,100)));
    for(int32 Index=0;Index<Count;++Index)Component->AddInstance(FTransform::Identity);
    return Component;
}

FTransform MotionTransform(double X,double Y,double Z,double Yaw=0.)
{
    return FTransform(FRotator(0,Yaw,0),FVector(X,Y,Z),FVector(1.6,1.6,1.2));
}

bool SameStoredTransform(UInstancedStaticMeshComponent* Component,int32 Index,const FTransform& Expected,bool Previous)
{
    FTransform Actual;
    const bool Found=Previous?Component->GetInstancePrevTransform(Index,Actual,true):Component->GetInstanceTransform(Index,Actual,true);
    // Rotation is undefined after reconstructing a zero-scale matrix.
    if(Expected.GetScale3D().IsNearlyZero())
        return Found&&Actual.GetScale3D().IsNearlyZero()&&Actual.GetLocation().Equals(Expected.GetLocation(),.001);
    return Found&&Actual.Equals(Expected,.001);
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRInstancePreviousFrame,"MPR.Sorter.Temporal.PreviousRenderedFrame",MPRInstanceMotionFlags)
bool FMPRInstancePreviousFrame::RunTest(const FString&)
{
    auto* Component=MakeMotionInstances(2);
    FMPRInstanceMotionHistory History;
    const TArray<FTransform> First={MotionTransform(100,200,300,15),MotionTransform(-200,450,200,80)};
    if(!TestTrue(TEXT("Initial transforms submit to engine instances"),History.Submit(Component,First,100)))return false;
    for(int32 Index=0;Index<First.Num();++Index)
    {
        TestTrue(TEXT("Initial current matrix is stored in the requested world space"),SameStoredTransform(Component,Index,First[Index],false));
        TestTrue(TEXT("First visible frame has no velocity from the initialization position"),SameStoredTransform(Component,Index,First[Index],true));
    }

    const TArray<FTransform> Second={MotionTransform(112,210,305,18),MotionTransform(-193,430,220,83)};
    TestTrue(TEXT("Next rendered frame submits"),History.Submit(Component,Second,101));
    for(int32 Index=0;Index<First.Num();++Index)
    {
        TestTrue(TEXT("Moving instance current matrix advances"),SameStoredTransform(Component,Index,Second[Index],false));
        TestTrue(TEXT("Moving instance previous matrix is the prior rendered position"),SameStoredTransform(Component,Index,First[Index],true));
    }

    const TArray<FTransform> SameFrame={MotionTransform(119,213,309,20),MotionTransform(-190,420,230,86)};
    TestTrue(TEXT("A second presentation update in one render frame succeeds"),History.Submit(Component,SameFrame,101));
    for(int32 Index=0;Index<First.Num();++Index)
    {
        TestTrue(TEXT("Same-frame resubmit stores its latest current position"),SameStoredTransform(Component,Index,SameFrame[Index],false));
        TestTrue(TEXT("Same-frame resubmit preserves the previous rendered frame instead of a simulation substep"),SameStoredTransform(Component,Index,First[Index],true));
    }

    const TArray<FTransform> Third={MotionTransform(128,220,314,22),MotionTransform(-185,410,240,89)};
    TestTrue(TEXT("Following rendered frame submits"),History.Submit(Component,Third,102));
    for(int32 Index=0;Index<First.Num();++Index)
        TestTrue(TEXT("Next frame follows the final submitted position of the preceding frame"),SameStoredTransform(Component,Index,SameFrame[Index],true));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRInstanceVisibilityIdentity,"MPR.Sorter.Temporal.VisibilityAndParcelIdentity",MPRInstanceMotionFlags)
bool FMPRInstanceVisibilityIdentity::RunTest(const FString&)
{
    auto* Component=MakeMotionInstances(2);
    FMPRInstanceMotionHistory History;
    const FTransform Hidden(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector);
    TArray<FTransform> Current={MotionTransform(100,200,300),MotionTransform(400,500,600)};
    TArray<uint64> Identities={11,22};
    if(!TestTrue(TEXT("Parcel pool initializes"),History.Submit(Component,Current,200,Identities)))return false;

    const FTransform OtherBeforeHide=Current[1];
    Current[0]=Hidden;Current[1]=MotionTransform(410,505,605);Identities[0]=0;
    TestTrue(TEXT("A departing parcel is hidden"),History.Submit(Component,Current,201,Identities));
    TestTrue(TEXT("Hiding a parcel does not produce a vector to the world origin"),SameStoredTransform(Component,0,Hidden,true));
    TestTrue(TEXT("Hiding one slot preserves the other parcel's history"),SameStoredTransform(Component,1,OtherBeforeHide,true));

    Current[0]=MotionTransform(2100,-1800,300);Identities[0]=11;
    TestTrue(TEXT("A hidden pool slot can become visible at its new location"),History.Submit(Component,Current,202,Identities));
    TestTrue(TEXT("Appearing parcel has no velocity from the hidden zero-scale transform"),SameStoredTransform(Component,0,Current[0],true));

    const FTransform SameParcelBeforeMove=Current[0];
    Current[0]=MotionTransform(2110,-1790,305);
    Current[1]=MotionTransform(-1800,1500,200);Identities[1]=23;
    TestTrue(TEXT("A reused visible slot accepts a different parcel"),History.Submit(Component,Current,203,Identities));
    TestTrue(TEXT("An unchanged parcel retains its movement history"),SameStoredTransform(Component,0,SameParcelBeforeMove,true));
    TestTrue(TEXT("New parcel identity never inherits another parcel's motion vector"),SameStoredTransform(Component,1,Current[1],true));

    Current[1]=MotionTransform(2800,-2500,200);Identities[1]=24;
    TestTrue(TEXT("Identity reuse within the same render frame is supported"),History.Submit(Component,Current,203,Identities));
    TestTrue(TEXT("Same-frame identity change also discards the unrelated previous parcel"),SameStoredTransform(Component,1,Current[1],true));

    const FTransform NewParcelBeforeMove=Current[1];
    Current[1]=MotionTransform(2815,-2480,210);
    TestTrue(TEXT("Replacement parcel resumes normal movement next frame"),History.Submit(Component,Current,204,Identities));
    TestTrue(TEXT("Replacement parcel history resumes from its own last position"),SameStoredTransform(Component,1,NewParcelBeforeMove,true));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRInstancePauseReset,"MPR.Sorter.Temporal.PauseAndReset",MPRInstanceMotionFlags)
bool FMPRInstancePauseReset::RunTest(const FString&)
{
    auto* Component=MakeMotionInstances(1);
    FMPRInstanceMotionHistory History;
    TArray<FTransform> Current={MotionTransform(100,200,300,10)};
    const TArray<uint64> Identities={1};
    if(!TestTrue(TEXT("Motion history initializes"),History.Submit(Component,Current,300,Identities)))return false;
    Current[0]=MotionTransform(125,215,320,20);
    TestTrue(TEXT("Moving frame submits"),History.Submit(Component,Current,301,Identities));
    TestTrue(TEXT("Paused frame resubmits the displayed pose"),History.Submit(Component,Current,302,Identities));
    TestTrue(TEXT("A paused instance clears its prior nonzero velocity"),SameStoredTransform(Component,0,Current[0],true));

    History.Reset();
    Current[0]=MotionTransform(-3100,4900,120,170);
    TestTrue(TEXT("Reset can reuse the first parcel identity in the same engine frame"),History.Submit(Component,Current,302,Identities));
    TestTrue(TEXT("Reset discards movement from the pre-reset location despite identical parcel ID"),SameStoredTransform(Component,0,Current[0],true));

    const FTransform ResetPosition=Current[0];
    Current[0]=MotionTransform(-3080,4880,130,172);
    TestTrue(TEXT("Animation resumes after reset"),History.Submit(Component,Current,303,Identities));
    TestTrue(TEXT("Motion after reset starts from the reset pose"),SameStoredTransform(Component,0,ResetPosition,true));

    // UE 5.8 ClearInstances does not clear PerInstancePrevTransform. Match the
    // distributor rebuild lifecycle so stale entries cannot disable dynamic data.
    Component->SetHasPerInstancePrevTransforms(false);
    Component->ClearInstances();
    Component->AddInstance(FTransform::Identity);
    History.Reset();
    Current[0]=MotionTransform(4500,3200,150,90);
    TestTrue(TEXT("Rebuilt instance pool enables fresh motion history"),History.Submit(Component,Current,304,Identities));
    TestTrue(TEXT("Rebuilt instance has no previous-generation velocity"),SameStoredTransform(Component,0,Current[0],true));
    FTransform Stale;
    TestFalse(TEXT("Rebuilt pool has no stale previous-transform entries beyond its current instance count"),Component->GetInstancePrevTransform(1,Stale,false));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRCartPresentationChanges,"MPR.Sorter.Presentation.CartChangedTransforms",MPRInstanceMotionFlags)
bool FMPRCartPresentationChanges::RunTest(const FString&)
{
    auto* Component=MakeMotionInstances(2);
    FMPRCartInstanceTransformCache Cart;
    const FTransform Docked=MotionTransform(1200,-400,100,20);
    const FTransform Withdrawn=MotionTransform(1200,-335,100,20);
    const FTransform Hidden(FQuat::Identity,Withdrawn.GetLocation(),FVector::ZeroVector);
    TestTrue(TEXT("Initial cart transform submits even if the slot already exists"),Cart.Submit(Component,0,Docked));
    for(int32 I=0;I<120;++I)
        TestFalse(TEXT("Unchanged docked cart does not submit another instance update"),Cart.Submit(Component,0,Docked));
    TestTrue(TEXT("Docked world-space pose remains unchanged"),SameStoredTransform(Component,0,Docked,false));
    TestTrue(TEXT("Withdrawing cart submits its moved position"),Cart.Submit(Component,0,Withdrawn));
    TestTrue(TEXT("Withdrawing world-space pose is exact"),SameStoredTransform(Component,0,Withdrawn,false));
    TestTrue(TEXT("Handoff hides the same cart slot"),Cart.Submit(Component,0,Hidden));
    TestFalse(TEXT("A held handoff does not repeat its hidden transform"),Cart.Submit(Component,0,Hidden));
    TestTrue(TEXT("Hidden slot retains its exit position"),SameStoredTransform(Component,0,Hidden,false));
    TestTrue(TEXT("Empty arriving cart becomes visible at the same position"),Cart.Submit(Component,0,Withdrawn));
    TestTrue(TEXT("Returning cart reaches its original dock"),Cart.Submit(Component,0,Docked));
    TestTrue(TEXT("Changing the instance mapping forces the identical world pose to the new slot"),Cart.Submit(Component,1,Docked));
    TestTrue(TEXT("New slot receives the mapped pose"),SameStoredTransform(Component,1,Docked,false));
    Component->SetWorldTransform(FTransform(FRotator(0,60,0),FVector(500,600,700)));
    TestTrue(TEXT("Parent transform changes preserve the requested cart world pose"),Cart.Submit(Component,1,Docked));
    TestTrue(TEXT("World pose is maintained after the parent moves"),SameStoredTransform(Component,1,Docked,false));
    Cart.Reset();
    TestTrue(TEXT("Reset forces an initial presentation without changing the slot mapping"),Cart.Submit(Component,1,Docked));
    auto* Rebuilt=MakeMotionInstances(2);
    TestTrue(TEXT("A rebuilt component cannot inherit another component's cached state"),Cart.Submit(Rebuilt,1,Docked));
    TestFalse(TEXT("Invalid slot does not change the cached valid submission"),Cart.Submit(Rebuilt,9,Withdrawn));
    TestFalse(TEXT("Valid unchanged slot still skips after the invalid call"),Cart.Submit(Rebuilt,1,Docked));
    TestEqual(TEXT("No cart instances were added or removed"),Component->GetInstanceCount(),2);
    TestEqual(TEXT("Rebuilt pool also retains its mapping"),Rebuilt->GetInstanceCount(),2);
    return true;
}
#endif
