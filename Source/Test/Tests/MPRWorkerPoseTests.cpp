#if WITH_DEV_AUTOMATION_TESTS
#include "../MPRWorkerPoseComponent.h"
#include "GHSAutomationTestFlags.h"
#include "Animation/AnimSequence.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/ScopeExit.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRWorkerGaitValidation,"MPR.Worker.DistanceDrivenGait",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRWorkerGaitValidation::RunTest(const FString&)
{
    using W=UMPRWorkerPoseComponent;
    TestTrue(TEXT("Idle feet do not step"),W::FootCycleOffset(123.,true,false).IsNearlyZero());
    for (bool Left:{false,true})
    {
        for (double Distance=-144.; Distance<288.; Distance+=.2)
        {
            const FVector A=W::FootCycleOffset(Distance,Left,true);
            TestTrue(TEXT("Sole does not go below floor"),A.Z>=-1.e-8);
            TestTrue(TEXT("Stride remains bounded"),FMath::Abs(A.X)<26. && A.Z<=5.51);
            TestTrue(TEXT("Cycle is periodic in travelled distance"),A.Equals(W::FootCycleOffset(Distance+72.,Left,true),1.e-7));
            const FVector B=W::FootCycleOffset(Distance+.001,Left,true);
            if (FMath::Abs(A.Z)<1.e-7 && FMath::Abs(B.Z)<1.e-7)
                TestTrue(TEXT("A planted foot cancels body travel, without skating"),FMath::Abs((B.X-A.X)+.001)<1.e-7);
        }
        for (double Boundary:{0.,44.64,72.})
        {
            const double Offset=Left?0.:-36.;
            const FVector Before=W::FootCycleOffset(Boundary+Offset-.0001,Left,true);
            const FVector After=W::FootCycleOffset(Boundary+Offset+.0001,Left,true);
            TestTrue(TEXT("Touchdown and lift-off have no position jump"),Before.Equals(After,.001));
        }
        for (double Scale:{.35,.1,1.})
        {
            for (double Distance=0.;Distance<72.*Scale;Distance+=.05)
            {
                const FVector A=W::FootCycleOffset(Distance,Left,true,Scale);
                const FVector B=W::FootCycleOffset(Distance+.0001,Left,true,Scale);
                if (A.Z<1.e-10&&B.Z<1.e-10)
                    TestTrue(TEXT("Short-step stance cancels all body translation"),FMath::Abs(B.X-A.X+.0001)<1.e-7);
            }
        }
    }
    TestTrue(TEXT("Zero stride weight is stable"),W::FootCycleOffset(17.,true,true,0.).IsNearlyZero());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRMannequinPoseValidation,"MPR.Worker.OfficialMannequinPose",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRMannequinPoseValidation::RunTest(const FString&)
{
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
    auto* Idle=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"));
    if (!TestNotNull(TEXT("Official Simple Manny is available"),Mesh)||!TestNotNull(TEXT("Engine is available"),GEngine)) return false;
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if (!TestNotNull(TEXT("Disposable world created"),World)) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World); World->DestroyWorld(false); };
    auto* Owner=World->SpawnActor<AActor>();
    if (!TestNotNull(TEXT("Disposable owner created"),Owner)) return false;
    auto* Worker=NewObject<UMPRWorkerPoseComponent>(Owner);
    Owner->SetRootComponent(Worker); Worker->RegisterComponent();
    if (!TestTrue(TEXT("Required arm, leg and finger chains resolve"),Worker->InitializeWorker(Mesh,Idle))) return false;
    TestFalse(TEXT("Worker has no clock independent of sorter pause/rate"),Worker->PrimaryComponentTick.bCanEverTick);

    for (double Yaw:{0.,90.,-45.})
    {
        FMPRWorkerPoseInput Pose;
        Pose.BodyWorld=FTransform(FRotator(0,Yaw,0),FVector(300,400,12));
        Pose.LeftPalmWorld=Pose.BodyWorld.TransformPosition(FVector(40,-12.1,105));
        Pose.RightPalmWorld=Pose.BodyWorld.TransformPosition(FVector(40,12.1,105));
        Pose.MoveDirectionWorld=Pose.BodyWorld.TransformVectorNoScale(FVector::RightVector);
        for (bool Push:{false,true})
        {
            Pose.bPushGrip=Push;
            Pose.TorsoLeanDegrees=Push?8.:5.;
            Pose.LeftPalmWorld=Pose.BodyWorld.TransformPosition(FVector(Push?22.:40.,Push?-22.:-12.1,105));
            Pose.RightPalmWorld=Pose.BodyWorld.TransformPosition(FVector(Push?22.:40.,Push?22.:12.1,105));
            for (double Distance=0.; Distance<72.; Distance+=6.)
            {
                Pose.TravelDistanceCm=Distance; Pose.bWalking=true;
                Worker->ApplyWorkerPose(Pose);
                TestTrue(TEXT("Actual left palm meets the supplied contact target"),Worker->GetPalmContactErrorCm(true)<.1);
                TestTrue(TEXT("Actual right palm meets the supplied contact target"),Worker->GetPalmContactErrorCm(false)<.1);
                TestTrue(TEXT("IK preserves original upper/lower limb lengths"),Worker->GetMaximumLimbLengthErrorCm()<.03);
                if (Push)
                {
                    for (const TCHAR* Bone:{TEXT("lowerarm_l"),TEXT("lowerarm_r")})
                    {
                        const FVector Elbow=Pose.BodyWorld.InverseTransformPosition(Worker->GetBoneTransform(Worker->GetBoneIndex(Bone)).GetLocation());
                        if (!TestTrue(TEXT("Short-reach cart grip keeps elbows out of the rear aisle boundary"),Elbow.X>=-5.))
                            AddInfo(FString::Printf(TEXT("Cart elbow: bone=%s yaw=%.2f distance=%.3f local=%s"),Bone,Yaw,Distance,*Elbow.ToString()));
                    }
                }
                for (bool Left:{false,true})
                {
                    const FVector Sole=Pose.BodyWorld.InverseTransformPosition(Worker->GetFootSoleWorld(Left));
                    const double ExpectedZ=UMPRWorkerPoseComponent::FootCycleOffset(Distance,Left,true).Z;
                    TestTrue(TEXT("Bone-derived sole meets its floor or swing height"),FMath::Abs(Sole.Z-ExpectedZ)<.1);
                }
            }
        }
        const FVector Left=Worker->GetPalmWorld(true),Right=Worker->GetPalmWorld(false),Foot=Worker->GetFootSoleWorld(true);
        const TArray<FTransform> First=Worker->GetComponentSpaceTransforms();
        Worker->ApplyWorkerPose(Pose);
        const TArray<FTransform>& Second=Worker->GetComponentSpaceTransforms();
        TestEqual(TEXT("Repeat sampling does not grow the bone pool"),First.Num(),Second.Num());
        for (int32 I=0; I<First.Num(); ++I)
            TestTrue(TEXT("Identical inputs give identical bones without frame accumulation"),First[I].Equals(Second[I],1.e-6));
        Pose.bVisible=false;
        const int32 Revision=Worker->GetPoseRevision();
        Pose.LeftPalmWorld+=FVector(100,200,300);
        Worker->ApplyWorkerPose(Pose);
        TestEqual(TEXT("Hidden exchange worker performs no bone refresh"),Worker->GetPoseRevision(),Revision);
        TestTrue(TEXT("Hidden worker does not follow a new target"),Worker->GetPalmWorld(true).Equals(Left,.001));
        TestTrue(TEXT("Other hand and planted foot retain their pose"),Worker->GetPalmWorld(false).Equals(Right,.001)&&Worker->GetFootSoleWorld(true).Equals(Foot,.001));
    }
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRMannequinHandoffSweep,"MPR.Worker.CADHandoffPoseSweep",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRMannequinHandoffSweep::RunTest(const FString&)
{
    FString Text;
    if (!TestTrue(TEXT("CAD fleet fixture is available"),FFileHelper::LoadFileToString(Text,*(FPaths::ProjectDir()/TEXT("SourceAssets/MPR/sorter_simulation/layout.json"))))) return false;
    TSharedPtr<FJsonObject> Layout;
    if (!TestTrue(TEXT("CAD fleet fixture parses"),FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Layout))||!Layout) return false;
    auto Vector=[](const TSharedPtr<FJsonObject>& Object,const TCHAR* Key)
    {
        const auto& A=Object->GetArrayField(Key);
        return FVector(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());
    };
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
    auto* Idle=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"));
    if (!TestNotNull(TEXT("Official mannequin is available for CAD sweep"),Mesh)||!TestNotNull(TEXT("Engine available"),GEngine)) return false;
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if (!TestNotNull(TEXT("Disposable sweep world"),World)) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World); World->DestroyWorld(false); };
    auto* Owner=World->SpawnActor<AActor>();
    if (!TestNotNull(TEXT("Disposable sweep owner"),Owner)) return false;
    auto* Worker=NewObject<UMPRWorkerPoseComponent>(Owner);Owner->SetRootComponent(Worker);Worker->RegisterComponent();
    if (!TestTrue(TEXT("Actual mannequin initialized for sweep"),Worker->InitializeWorker(Mesh,Idle))) return false;
    double MaximumPalmError=0.,MaximumLengthError=0.,MaximumSoleError=0.;int32 Samples=0,Failures=0;
    const auto Profiles=Layout->GetObjectField(TEXT("profiles"));
    for (const auto& Value:Layout->GetArrayField(TEXT("machines")))
    {
        const auto Machine=Value->AsObject(),Profile=Profiles->GetObjectField(Machine->GetStringField(TEXT("profile")));
        const auto Saved=Machine->GetObjectField(TEXT("world_transform"));const auto& Q=Saved->GetArrayField(TEXT("rotation_xyzw"));
        const FTransform MachineWorld(FQuat(Q[0]->AsNumber(),Q[1]->AsNumber(),Q[2]->AsNumber(),Q[3]->AsNumber()),Vector(Saved,TEXT("translation_cm")),Vector(Saved,TEXT("scale")));
        const double Side=Machine->GetNumberField(TEXT("infeed_side_local_x"));
        const FVector Pickup=MachineWorld.InverseTransformPosition(Vector(Machine,TEXT("pickup_ue_cm")));
        const FVector Entry=MachineWorld.InverseTransformPosition(Vector(Machine,TEXT("entry_ue_cm")));
        const FVector Load(Side*(Profile->GetNumberField(TEXT("track_half_straight_cm"))+Profile->GetNumberField(TEXT("track_radius_cm"))),0,Profile->GetNumberField(TEXT("infeed_height_cm")));
        FVector StartFeet(Pickup.X-Side*50.,Pickup.Y-27.,0),EndFeet(Entry.X+Side*28.,Load.Y-27.,0);
        const bool Walking=Machine->GetStringField(TEXT("profile"))==TEXT("cad64");
        if (!Walking) StartFeet.X=EndFeet.X=(StartFeet.X+EndFeet.X)*.5;
        for (int32 Frame=0;Frame<=40;++Frame)
        {
            const double T=Frame/40.;
            const FVector Parcel=FMath::Lerp(Pickup+FVector(0,0,2.8),Load+FVector(0,0,2.8),T)+FVector(0,0,12*FMath::Sin(PI*T));
            const FVector Feet=FMath::Lerp(StartFeet,EndFeet,T);
            const double Heading=FMath::Atan2(Parcel.Y-Feet.Y,Parcel.X-Feet.X);
            const FQuat Facing(FVector::UpVector,Heading),BoxTurn(FVector::UpVector,Side*PI*.5*T);
            const FVector LeftDirection=-Facing.RotateVector(FVector::RightVector),BoxDirection=BoxTurn.UnrotateVector(LeftDirection);
            const double HalfWidth=FMath::Min(11./FMath::Max(FMath::Abs(BoxDirection.X),1.e-6),8./FMath::Max(FMath::Abs(BoxDirection.Y),1.e-6));
            FMPRWorkerPoseInput Pose;
            Pose.BodyWorld=FTransform(Facing,Feet)*MachineWorld;
            Pose.LeftPalmWorld=MachineWorld.TransformPosition(Parcel+LeftDirection*(HalfWidth+.25)-FVector(0,0,.5));
            Pose.RightPalmWorld=MachineWorld.TransformPosition(Parcel-LeftDirection*(HalfWidth+.25)-FVector(0,0,.5));
            Pose.MoveDirectionWorld=MachineWorld.TransformVectorNoScale((EndFeet-StartFeet).GetSafeNormal());
            Pose.bWalking=Walking;Pose.TravelDistanceCm=FVector::Dist2D(StartFeet,Feet);Pose.TorsoLeanDegrees=16.;
            auto Ease=[](double X){X=FMath::Clamp(X,0.,1.);return X*X*(3.-2.*X);};
            Pose.GaitBlend=.35*Ease(T/.15)*Ease((1.-T)/.15);
            Worker->ApplyWorkerPose(Pose);
            const double Left=Worker->GetPalmContactErrorCm(true),Right=Worker->GetPalmContactErrorCm(false),Length=Worker->GetMaximumLimbLengthErrorCm();
            double Sole=0.;
            for (bool IsLeft:{false,true})
            {
                const double Expected=UMPRWorkerPoseComponent::FootCycleOffset(Pose.TravelDistanceCm,IsLeft,Walking,Pose.GaitBlend).Z;
                Sole=FMath::Max(Sole,FMath::Abs(Pose.BodyWorld.InverseTransformPosition(Worker->GetFootSoleWorld(IsLeft)).Z-Expected));
            }
            MaximumPalmError=FMath::Max(MaximumPalmError,FMath::Max(Left,Right));MaximumLengthError=FMath::Max(MaximumLengthError,Length);MaximumSoleError=FMath::Max(MaximumSoleError,Sole);++Samples;
            if (Left>.1||Right>.1||Length>.03||Sole>.1)
            {
                ++Failures;
                if (Failures<=8)
                {
                    AddError(FString::Printf(TEXT("CAD handoff pose failed: machine=%s profile=%s side=%.0f t=%.3f feet=%s parcel=%s heading=%.3f left=%.6fcm right=%.6fcm bone=%.6fcm sole=%.6fcm"),
                        *Machine->GetStringField(TEXT("id")),*Machine->GetStringField(TEXT("profile")),Side,T,*Feet.ToString(),*Parcel.ToString(),FMath::RadiansToDegrees(Heading),Left,Right,Length,Sole));
                    for (bool IsLeft:{true,false})
                    {
                        const FVector Shoulder=Worker->GetBoneTransform(Worker->GetBoneIndex(IsLeft?TEXT("upperarm_l"):TEXT("upperarm_r"))).GetLocation();
                        const FVector Elbow=Worker->GetBoneTransform(Worker->GetBoneIndex(IsLeft?TEXT("lowerarm_l"):TEXT("lowerarm_r"))).GetLocation();
                        const FVector Wrist=Worker->GetBoneTransform(Worker->GetBoneIndex(IsLeft?TEXT("hand_l"):TEXT("hand_r"))).GetLocation();
                        const FVector DesiredWrist=Wrist+(IsLeft?Pose.LeftPalmWorld:Pose.RightPalmWorld)-Worker->GetPalmWorld(IsLeft);
                        const double ArmLength=FVector::Distance(Shoulder,Elbow)+FVector::Distance(Elbow,Wrist);
                        AddInfo(FString::Printf(TEXT("%s arm measured: shoulder=%s elbow=%s wrist=%s targetWrist=%s length=%.6fcm requiredDistance=%.6fcm"),
                            IsLeft?TEXT("Left"):TEXT("Right"),*Shoulder.ToString(),*Elbow.ToString(),*Wrist.ToString(),*DesiredWrist.ToString(),ArmLength,FVector::Distance(Shoulder,DesiredWrist)));
                    }
                }
            }
        }
    }
    AddInfo(FString::Printf(TEXT("CAD pose sweep: %d samples across all 22 machines, %d failed samples, max palm %.9fcm, bone %.9fcm, sole %.9fcm"),Samples,Failures,MaximumPalmError,MaximumLengthError,MaximumSoleError));
    return TestEqual(TEXT("All profiles, both loading sides and full transfer sweeps checked"),Samples,22*41)
        &&TestEqual(TEXT("Every real CAD transfer pose preserves palm contact, limbs and floor support"),Failures,0);
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRMannequinFootSupport,"MPR.Worker.SmallStrideFootSupport",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRMannequinFootSupport::RunTest(const FString&)
{
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
    auto* Idle=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"));
    if (!TestNotNull(TEXT("Official mannequin is available for foot support test"),Mesh)||!TestNotNull(TEXT("Engine available"),GEngine)) return false;
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if (!TestNotNull(TEXT("Disposable support world"),World)) return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World);World->DestroyWorld(false); };
    auto* Owner=World->SpawnActor<AActor>();
    if (!TestNotNull(TEXT("Disposable support owner"),Owner)) return false;
    auto* Worker=NewObject<UMPRWorkerPoseComponent>(Owner);Owner->SetRootComponent(Worker);Worker->RegisterComponent();
    if (!TestTrue(TEXT("Official component ready"),Worker->InitializeWorker(Mesh,Idle))) return false;
    int32 StancePairs=0;double MaxDrift=0.;
    for (double Yaw:{0.,90.,-45.}) for (double Scale:{1.,.35}) for (bool Sideways:{false,true})
    {
        const FQuat Facing(FVector::UpVector,FMath::DegreesToRadians(Yaw));
        const FVector Direction=Facing.RotateVector(Sideways?FVector::RightVector:FVector::ForwardVector);
        FVector Previous[2]={FVector::ZeroVector,FVector::ZeroVector};
        for (int32 Frame=0;Frame<=240;++Frame)
        {
            const double Distance=Frame*.2;
            FMPRWorkerPoseInput Pose;
            Pose.BodyWorld=FTransform(Facing,FVector(300,400,12)+Direction*Distance);
            Pose.LeftPalmWorld=Pose.BodyWorld.TransformPosition(FVector(40,-12.1,105));
            Pose.RightPalmWorld=Pose.BodyWorld.TransformPosition(FVector(40,12.1,105));
            Pose.MoveDirectionWorld=Direction;Pose.TravelDistanceCm=Distance;Pose.bWalking=true;Pose.GaitBlend=Scale;
            Pose.TorsoLeanDegrees=10.;Pose.SimulationTime=Frame/60.;
            Worker->ApplyWorkerPose(Pose);
            for (int32 Side=0;Side<2;++Side)
            {
                const bool Left=Side==0;
                const FVector Current=Worker->GetFootSoleWorld(Left);
                const auto Ground=[Left,Scale](double D){return UMPRWorkerPoseComponent::FootCycleOffset(D,Left,true,Scale).Z<1.e-10;};
                if (Frame>0&&Ground(Distance)&&Ground(Distance-.1)&&Ground(Distance-.2))
                {
                    const double Drift=FVector::Distance(Current,Previous[Side]);
                    MaxDrift=FMath::Max(MaxDrift,Drift);++StancePairs;
                    if (Drift>.03||FMath::Abs(Current.Z-12.)>.03)
                    {
                        AddError(FString::Printf(TEXT("Planted actual sole slipped: yaw=%.1f scale=%.2f sideways=%d left=%d distance=%.3f previous=%s actual=%s drift=%.6fcm"),
                            Yaw,Scale,Sideways,Left,Distance,*Previous[Side].ToString(),*Current.ToString(),Drift));
                        return false;
                    }
                }
                Previous[Side]=Current;
            }
        }
    }
    AddInfo(FString::Printf(TEXT("Actual mannequin stance: %d grounded frame pairs, max world sole drift=%.9fcm"),StancePairs,MaxDrift));
    return TestTrue(TEXT("Both full and 0.35 strides had actual grounded support samples"),StancePairs>1000);
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMPRWorkerDisplayLODValidation,"MPR.Worker.DisplayLODWithoutPoseTick",
    GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FMPRWorkerDisplayLODValidation::RunTest(const FString&)
{
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
    if(!TestNotNull(TEXT("Official worker mesh available"),Mesh)||!TestNotNull(TEXT("Engine available"),GEngine))return false;
    if(!TestTrue(TEXT("Existing worker mesh has near and far LODs"),Mesh->GetLODNum()>1))return false;
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false)
        .ShouldSimulatePhysics(false).CreateNavigation(false).CreateAISystem(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Disposable world available"),World))return false;
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    ON_SCOPE_EXIT { GEngine->DestroyWorldContext(World);World->DestroyWorld(false); };
    auto* Owner=World->SpawnActor<AActor>();
    auto* Worker=NewObject<UMPRWorkerPoseComponent>(Owner);Owner->SetRootComponent(Worker);Worker->RegisterComponent();
    if(!TestTrue(TEXT("Worker initializes"),Worker->InitializeWorker(Mesh)))return false;
    FMPRWorkerPoseInput Pose;
    Pose.BodyWorld=FTransform(FRotator(0,30,0),FVector(1000,-700,0));
    Pose.LeftPalmWorld=Pose.BodyWorld.TransformPosition(FVector(25,-18,107));
    Pose.RightPalmWorld=Pose.BodyWorld.TransformPosition(FVector(25,18,107));
    Pose.GripAlpha=0.;Pose.TorsoLeanDegrees=3.;Worker->ApplyWorkerPose(Pose);
    const auto Bones=Worker->GetComponentSpaceTransforms();
    const FTransform WorldPose=Worker->GetComponentTransform();
    const int32 Revision=Worker->GetPoseRevision();
    // Deterministic renderer-feedback fixture. Actual camera-driven MinDesiredLOD
    // changes are additionally checked in the native scene by moving near/far.
    Worker->bUseScreenRenderStateForUpdate=false;
    Worker->SetLastRenderTime(World->GetTimeSeconds());
    Worker->SetForcedLOD(Mesh->GetLODNum());
    TestTrue(TEXT("A far display LOD is applied without enabling component tick"),Worker->UpdatePresentationLOD());
    TestEqual(TEXT("Renderer can select the existing coarsest LOD"),Worker->GetPredictedLODLevel(),Mesh->GetLODNum()-1);
    const int32 Changes=Worker->GetDisplayLODChanges();
    for(int32 I=0;I<120;++I)TestFalse(TEXT("An unchanged LOD produces no further upload request"),Worker->UpdatePresentationLOD());
    TestEqual(TEXT("Stationary LOD change counter remains stable"),Worker->GetDisplayLODChanges(),Changes);
    Worker->SetForcedLOD(1);
    TestTrue(TEXT("Returning near restores full existing detail"),Worker->UpdatePresentationLOD());
    TestEqual(TEXT("Near LOD is zero"),Worker->GetPredictedLODLevel(),0);
    TestFalse(TEXT("LOD maintenance does not create an independent animation tick"),Worker->PrimaryComponentTick.bCanEverTick);
    TestEqual(TEXT("LOD maintenance never reruns procedural pose solving"),Worker->GetPoseRevision(),Revision);
    TestTrue(TEXT("Worker placement remains identical"),Worker->GetComponentTransform().Equals(WorldPose,1.e-9));
    const auto& After=Worker->GetComponentSpaceTransforms();
    TestEqual(TEXT("Full bone data remains available across LODs"),After.Num(),Bones.Num());
    for(int32 I=0;I<Bones.Num();++I)TestTrue(TEXT("Every existing bone pose is preserved"),After[I].Equals(Bones[I],1.e-9));
    Worker->SetVisibility(false,true);Worker->SetForcedLOD(Mesh->GetLODNum());
    TestFalse(TEXT("Hidden exchange worker performs no LOD maintenance"),Worker->UpdatePresentationLOD());
    Worker->SetVisibility(true,true);Worker->SetLastRenderTime(World->GetTimeSeconds()-2.f);
    TestFalse(TEXT("An offscreen worker does not consume a LOD it cannot upload"),Worker->UpdatePresentationLOD());
    Worker->SetLastRenderTime(World->GetTimeSeconds());
    TestTrue(TEXT("Returning onscreen applies the pending LOD"),Worker->UpdatePresentationLOD());
    Worker->SetForcedLOD(0);
    return true;
}
#endif
