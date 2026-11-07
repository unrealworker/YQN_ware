#include "MPRWorkerPoseComponent.h"

#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Engine/SkeletalMesh.h"
#include "TwoBoneIK.h"

namespace
{
constexpr double GaitCycleDistance = 72.;
constexpr double StanceFraction = .62;

FQuat FrameRotation(const FVector& Finger, const FVector& Normal)
{
    return FRotationMatrix::MakeFromXZ(Finger, Normal).ToQuat();
}
}

UMPRWorkerPoseComponent::UMPRWorkerPoseComponent()
{
    // No independent animation clock: pause, reset and rate are owned by the sorter.
    PrimaryComponentTick.bCanEverTick = false;
    SetCollisionEnabled(ECollisionEnabled::NoCollision);
    SetGenerateOverlapEvents(false);
    SetCanEverAffectNavigation(false);
    SetCastShadow(true);
    bAffectDistanceFieldLighting = false;
    bAffectDynamicIndirectLighting = false;
}

bool UMPRWorkerPoseComponent::InitializeWorker(USkeletalMesh* Mesh, UAnimSequence* OptionalIdle)
{
    bPoseReady = false;
    if (!Mesh) return false;
    SetSkinnedAssetAndUpdate(Mesh);
    if (!AllocateTransformData()) return false;

    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    ReferenceLocal = Ref.GetRefBonePose();
    BaseLocal = ReferenceLocal;
    Parents.SetNum(Ref.GetNum());
    for (int32 I=0; I<Ref.GetNum(); ++I) Parents[I] = Ref.GetParentIndex(I);
    WorkingLocal = ReferenceLocal;
    BuildComponentPose();
    ReferenceComponent = WorkingComponent;

    // A fixed sample supplies the actual mannequin's relaxed body/finger baseline.
    // Preserve reference translations/scales so sampling cannot resize any bone.
    if (OptionalIdle && OptionalIdle->GetSkeleton() == Mesh->GetSkeleton())
    {
        const FAnimExtractContext Extract(0.);
        for (int32 I=1; I<Ref.GetNum(); ++I)
        {
            const int32 SkeletonIndex = OptionalIdle->GetSkeleton()->GetSkeletonBoneIndexFromMeshBoneIndex(Mesh, I);
            if (SkeletonIndex == INDEX_NONE) continue;
            FTransform Sample = ReferenceLocal[I];
            OptionalIdle->GetBoneTransform(Sample, FSkeletonPoseBoneIndex(SkeletonIndex), Extract, false);
            // Raw data without a track can yield identity. Reject that absent-track
            // value instead of collapsing a reference bone's orientation.
            if (!Sample.ContainsNaN() && Sample.GetRotation().IsNormalized()
                && Sample.GetTranslation().Equals(ReferenceLocal[I].GetTranslation(), 5.))
                BaseLocal[I].SetRotation(Sample.GetRotation());
        }
    }

    auto Index = [&Ref](const TCHAR* Name) { return Ref.FindBoneIndex(FName(Name)); };
    auto Limb = [this, &Index](FLimb& L, const TCHAR* Upper, const TCHAR* Lower, const TCHAR* End)
    {
        L.Upper=Index(Upper); L.Lower=Index(Lower); L.End=Index(End);
        if (L.Upper==INDEX_NONE || L.Lower==INDEX_NONE || L.End==INDEX_NONE) return false;
        if (Parents[L.Lower]!=L.Upper || Parents[L.End]!=L.Lower) return false;
        L.UpperLength=FVector::Distance(ReferenceComponent[L.Upper].GetLocation(), ReferenceComponent[L.Lower].GetLocation());
        L.LowerLength=FVector::Distance(ReferenceComponent[L.Lower].GetLocation(), ReferenceComponent[L.End].GetLocation());
        return L.UpperLength>1. && L.LowerLength>1.;
    };
    if (!Limb(Hands[0].Arm,TEXT("upperarm_l"),TEXT("lowerarm_l"),TEXT("hand_l"))
        || !Limb(Hands[1].Arm,TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r"))
        || !Limb(Legs[0],TEXT("thigh_l"),TEXT("calf_l"),TEXT("foot_l"))
        || !Limb(Legs[1],TEXT("thigh_r"),TEXT("calf_r"),TEXT("foot_r"))) return false;

    // Infer the real mesh forward axis from the feet. This avoids assuming that
    // Manny's imported axes match an Actor's conventional +X forward.
    const int32 Balls[2] = {Index(TEXT("ball_l")), Index(TEXT("ball_r"))};
    ToeBones[0]=Balls[0]; ToeBones[1]=Balls[1];
    FVector FootDirection=FVector::ZeroVector;
    for (int32 Side=0; Side<2; ++Side)
        if (Balls[Side]!=INDEX_NONE)
            FootDirection += ReferenceComponent[Balls[Side]].GetLocation()-ReferenceComponent[Legs[Side].End].GetLocation();
    FootDirection.Z=0.;
    if (FootDirection.IsNearlyZero()) return false;
    ReferenceForward=FootDirection.GetSafeNormal();
    ReferenceFacingYawDegrees=FMath::RadiansToDegrees(FMath::Atan2(ReferenceForward.Y,ReferenceForward.X));
    MeshToBody=FQuat(FVector::UpVector,-FMath::DegreesToRadians(ReferenceFacingYawDegrees));
    Spine[0]=Index(TEXT("spine_01")); Spine[1]=Index(TEXT("spine_03")); Spine[2]=Index(TEXT("spine_05"));
    Pelvis=Index(TEXT("pelvis"));

    for (int32 Side=0; Side<2; ++Side)
    {
        FHand& H=Hands[Side];
        const TCHAR* Suffix=Side==0?TEXT("l"):TEXT("r");
        auto FingerIndex=[&Ref,Suffix](const TCHAR* Finger, int32 Segment)
        { return Ref.FindBoneIndex(FName(*FString::Printf(TEXT("%s_%02d_%s"),Finger,Segment,Suffix))); };
        const int32 Middle=FingerIndex(TEXT("middle"),1), IndexFinger=FingerIndex(TEXT("index"),1), Pinky=FingerIndex(TEXT("pinky"),1);
        if (Middle==INDEX_NONE || IndexFinger==INDEX_NONE || Pinky==INDEX_NONE) return false;
        const FTransform& Wrist=ReferenceComponent[H.Arm.End];
        H.FingerDirection=(ReferenceComponent[Middle].GetLocation()-Wrist.GetLocation()).GetSafeNormal();
        const FVector Across=ReferenceComponent[IndexFinger].GetLocation()-ReferenceComponent[Pinky].GetLocation();
        H.PalmNormal=FVector::CrossProduct(H.FingerDirection,Across).GetSafeNormal();
        // The open reference palm is the underside of the A-pose hand. A lower
        // normal is deterministic on both mirrored hands and keeps curls inward.
        if (H.PalmNormal.Z>0.) H.PalmNormal *= -1.;
        const FVector Palm=FMath::Lerp(Wrist.GetLocation(),ReferenceComponent[Middle].GetLocation(),.55);
        H.PalmLocal=Wrist.InverseTransformPosition(Palm);
        H.Fingers.Reset(); H.CurlAxesLocal.Reset();
        for (const TCHAR* Finger : {TEXT("index"),TEXT("middle"),TEXT("ring"),TEXT("pinky"),TEXT("thumb")})
            for (int32 Segment=1; Segment<=3; ++Segment)
            {
                const int32 Bone=FingerIndex(Finger,Segment);
                if (Bone==INDEX_NONE) continue;
                const int32 Next=FingerIndex(Finger,Segment+1);
                const FVector Direction=Next==INDEX_NONE?H.FingerDirection:
                    (ReferenceComponent[Next].GetLocation()-ReferenceComponent[Bone].GetLocation()).GetSafeNormal();
                FVector Axis=FVector::CrossProduct(Direction,H.PalmNormal).GetSafeNormal();
                if (Axis.IsNearlyZero()) Axis=FVector::RightVector;
                H.Fingers.Add(Bone);
                H.CurlAxesLocal.Add(ReferenceComponent[Bone].GetRotation().UnrotateVector(Axis));
            }

        const FTransform& Foot=ReferenceComponent[Legs[Side].End];
        // Floor zero is the mannequin root plane. Readback uses the same sole
        // contact point as the leg solve rather than treating an ankle as a sole.
        FVector Sole=Foot.GetLocation(); Sole.Z=ReferenceComponent[0].GetLocation().Z;
        SoleLocal[Side]=Foot.InverseTransformPosition(Sole);
    }
    WorkingLocal=BaseLocal;
    BuildComponentPose();
    bPoseReady=true;
    return true;
}

void UMPRWorkerPoseComponent::BuildComponentPose()
{
    WorkingComponent.SetNumUninitialized(WorkingLocal.Num());
    for (int32 I=0; I<WorkingLocal.Num(); ++I)
        WorkingComponent[I]=Parents[I]==INDEX_NONE?WorkingLocal[I]:WorkingLocal[I]*WorkingComponent[Parents[I]];
}

void UMPRWorkerPoseComponent::SetComponentBone(int32 Bone, const FTransform& Transform)
{
    if (!WorkingLocal.IsValidIndex(Bone)) return;
    WorkingLocal[Bone]=Parents[Bone]==INDEX_NONE?Transform:Transform.GetRelativeTransform(WorkingComponent[Parents[Bone]]);
    WorkingLocal[Bone].NormalizeRotation();
    BuildComponentPose();
}

void UMPRWorkerPoseComponent::RotateComponentBone(int32 Bone, const FQuat& Delta)
{
    if (!WorkingLocal.IsValidIndex(Bone)) return;
    FTransform T=WorkingComponent[Bone];
    T.SetRotation((Delta*T.GetRotation()).GetNormalized());
    SetComponentBone(Bone,T);
}

void UMPRWorkerPoseComponent::SolveLimb(const FLimb& Limb, const FVector& Target, const FVector& Pole, const FQuat& EndRotation)
{
    FTransform Upper=WorkingComponent[Limb.Upper], Lower=WorkingComponent[Limb.Lower], End=WorkingComponent[Limb.End];
    AnimationCore::SolveTwoBoneIK(Upper,Lower,End,Pole,Target,Limb.UpperLength,Limb.LowerLength,false,1.,1.);
    End.SetRotation(EndRotation);
    // Parent first; each child is converted against its already solved parent.
    SetComponentBone(Limb.Upper,Upper);
    SetComponentBone(Limb.Lower,Lower);
    SetComponentBone(Limb.End,End);
}

void UMPRWorkerPoseComponent::PoseHand(int32 Side, const FVector& Target, const FVector& Inward, double Grip, bool bPushGrip)
{
    const FHand& H=Hands[Side];
    FVector Normal=Inward.GetSafeNormal();
    FVector Fingers=-FVector::UpVector;
    if (FMath::Abs(FVector::DotProduct(Fingers,Normal))>.9) Fingers=ReferenceForward;
    const FQuat DesiredRotation=(FrameRotation(Fingers,Normal)*FrameRotation(H.FingerDirection,H.PalmNormal).Inverse()
        *ReferenceComponent[H.Arm.End].GetRotation()).GetNormalized();
    const FVector WristTarget=Target-DesiredRotation.RotateVector(H.PalmLocal);
    const FVector BodyRight=FVector::CrossProduct(FVector::UpVector,ReferenceForward);
    const double Sign=Side==0?-1.:1.;
    const FVector Shoulder=WorkingComponent[H.Arm.Upper].GetLocation();
    // In the narrow cart aisle, fold elbows toward the held frame instead of
    // projecting them backwards into the neighbouring docked cart.
    const FVector Pole=Shoulder+BodyRight*(Sign*(bPushGrip?26.:36.))
        +ReferenceForward*(bPushGrip?22.:-14.)-FVector(0,0,bPushGrip?34.:42.);
    SolveLimb(H.Arm,WristTarget,Pole,DesiredRotation);

    for (int32 I=0; I<H.Fingers.Num(); ++I)
    {
        const int32 Bone=H.Fingers[I];
        // Mild curl: the fingers wrap the parcel edge without making a fist
        // inside a thin carton. Keep each phalanx's original local translation.
        const double Degrees=(I%3==0?18.:I%3==1?24.:18.)*Grip;
        WorkingLocal[Bone].SetRotation((ReferenceLocal[Bone].GetRotation()
            *FQuat(H.CurlAxesLocal[I],FMath::DegreesToRadians(Degrees))).GetNormalized());
    }
    BuildComponentPose();
}

FVector UMPRWorkerPoseComponent::FootCycleOffset(double DistanceCm, bool bLeft, bool bWalking, double StrideScale)
{
    if (!bWalking || !FMath::IsFinite(DistanceCm) || !FMath::IsFinite(StrideScale) || StrideScale<=1.e-5)
        return FVector::ZeroVector;
    StrideScale=FMath::Clamp(StrideScale,0.,1.);
    // A shorter stride must also have a shorter travelled-distance period.
    // Merely multiplying the offsets by a weight would leave (1-weight) of
    // the body's travel in a planted foot and make small steps skate.
    const double CycleDistance=GaitCycleDistance*StrideScale;
    double Phase=FMath::Fmod(DistanceCm/CycleDistance+(bLeft?0.:.5),1.);
    if (Phase<0.) Phase+=1.;
    const double Length=CycleDistance*StanceFraction;
    if (Phase<StanceFraction)
        return FVector(Length*.5-Phase*CycleDistance,0,0);
    const double T=(Phase-StanceFraction)/(1.-StanceFraction);
    // Hermite endpoint tangents cancel body velocity at lift-off / touchdown.
    const double Tangent=-CycleDistance*(1.-StanceFraction);
    const double X=(2*T*T*T-3*T*T+1)*(-Length*.5)+(T*T*T-2*T*T+T)*Tangent
        +(-2*T*T*T+3*T*T)*(Length*.5)+(T*T*T-T*T)*Tangent;
    return FVector(X,0,5.5*StrideScale*FMath::Square(FMath::Sin(PI*T)));
}

void UMPRWorkerPoseComponent::ApplyWorkerPose(const FMPRWorkerPoseInput& Input)
{
    SetVisibility(Input.bVisible,true);
    SetHiddenInGame(!Input.bVisible,true);
    if (!bPoseReady || !Input.bVisible) return;
    if (Input.BodyWorld.ContainsNaN() || Input.LeftPalmWorld.ContainsNaN() || Input.RightPalmWorld.ContainsNaN()) return;
    const FTransform ComponentWorld=FTransform(MeshToBody)*Input.BodyWorld;
    SetWorldTransform(ComponentWorld);
    LastPalmTargets[0]=Input.LeftPalmWorld; LastPalmTargets[1]=Input.RightPalmWorld;
    const FVector Targets[2]={ComponentWorld.InverseTransformPosition(Input.LeftPalmWorld),ComponentWorld.InverseTransformPosition(Input.RightPalmWorld)};
    const FVector BodyTarget=Input.BodyWorld.InverseTransformPosition((Input.LeftPalmWorld+Input.RightPalmWorld)*.5);
    const double Turn=FMath::Clamp(FMath::Atan2(BodyTarget.Y,FMath::Max(BodyTarget.X,1.)),-.4,.4);
    const double Lean=FMath::DegreesToRadians(FMath::Clamp(Input.TorsoLeanDegrees,0.,16.));
    const double GaitWeight=Input.bWalking?FMath::Clamp(Input.GaitBlend,0.,1.):0.;
    const FVector Right=FVector::CrossProduct(FVector::UpVector,ReferenceForward);

    WorkingLocal=BaseLocal;
    BuildComponentPose();
    // Bend the knees when reaching a low carton. Bringing the shoulder down
    // provides reach through posture rather than lengthening the mannequin's
    // arms. The leg IK keeps the soles on the original ground plane.
    if (Pelvis!=INDEX_NONE)
    {
        FTransform Hip=WorkingComponent[Pelvis];
        const double LowGrip=FMath::Clamp(Input.GripAlpha,0.,1.)*FMath::Clamp(Input.TorsoLeanDegrees/16.,0.,1.);
        const double HipDrop=2.+FMath::Max(4.*GaitWeight,10.*LowGrip);
        // Shift weight over the balls of the planted feet while reaching. This
        // gives a low carton a natural forward reach without moving the worker
        // out of the CAD aisle or stretching either arm.
        Hip.AddToTranslation(ReferenceForward*(Input.bPushGrip?0.:8.*LowGrip)+FVector(0,0,-HipDrop));
        SetComponentBone(Pelvis,Hip);
    }
    for (int32 Bone:Spine)
        RotateComponentBone(Bone,FQuat(FVector::UpVector,Turn/3.)*FQuat(Right,Lean/3.));

    FVector Travel=ComponentWorld.InverseTransformVectorNoScale(Input.MoveDirectionWorld); Travel.Z=0.;
    Travel=Travel.GetSafeNormal();
    if (Travel.IsNearlyZero()) Travel=ReferenceForward;
    for (int32 Side=0; Side<2; ++Side)
    {
        const FLimb& L=Legs[Side];
        const FTransform& RefFoot=ReferenceComponent[L.End];
        const FVector Cycle=FootCycleOffset(Input.TravelDistanceCm,Side==0,Input.bWalking,GaitWeight);
        FVector Ankle=RefFoot.GetLocation()+Travel*Cycle.X+FVector(0,0,Cycle.Z);
        const FVector KneePole=WorkingComponent[L.Upper].GetLocation()+ReferenceForward*75.-FVector(0,0,18.);
        SolveLimb(L,Ankle,KneePole,RefFoot.GetRotation());
        if (ToeBones[Side]!=INDEX_NONE)
            WorkingLocal[ToeBones[Side]]=ReferenceLocal[ToeBones[Side]];
    }

    PoseHand(0,Targets[0],Input.bPushGrip?ReferenceForward:Targets[1]-Targets[0],FMath::Clamp(Input.GripAlpha,0.,1.),Input.bPushGrip);
    PoseHand(1,Targets[1],Input.bPushGrip?ReferenceForward:Targets[0]-Targets[1],FMath::Clamp(Input.GripAlpha,0.,1.),Input.bPushGrip);

    // UPoseableMeshComponent otherwise allocates a parent pose for each named
    // setter. Commit the whole local pose once and refresh its render data once.
    BoneSpaceTransforms=WorkingLocal;
    MarkRefreshTransformDirty();
    RefreshBoneTransforms();
    ++PoseRevision;
}

FVector UMPRWorkerPoseComponent::GetPalmWorld(bool bLeft) const
{
    if (!bPoseReady) return FVector::ZeroVector;
    const FHand& H=Hands[bLeft?0:1];
    return GetBoneTransform(H.Arm.End).TransformPosition(H.PalmLocal);
}

FVector UMPRWorkerPoseComponent::GetFootSoleWorld(bool bLeft) const
{
    if (!bPoseReady) return FVector::ZeroVector;
    const int32 Side=bLeft?0:1;
    return GetBoneTransform(Legs[Side].End).TransformPosition(SoleLocal[Side]);
}

double UMPRWorkerPoseComponent::GetPalmContactErrorCm(bool bLeft) const
{
    return bPoseReady?FVector::Distance(GetPalmWorld(bLeft),LastPalmTargets[bLeft?0:1]):-1.;
}

double UMPRWorkerPoseComponent::GetMaximumLimbLengthErrorCm() const
{
    if (!bPoseReady) return -1.;
    double Error=0.;
    for (const FLimb* L:{&Hands[0].Arm,&Hands[1].Arm,&Legs[0],&Legs[1]})
    {
        const FVector A=GetBoneTransform(L->Upper).GetLocation(),B=GetBoneTransform(L->Lower).GetLocation(),C=GetBoneTransform(L->End).GetLocation();
        // The MPR fleet uses unit scale. Compare in component space to also
        // make this diagnostic meaningful under a uniformly scaled parent.
        const FTransform& World=GetComponentTransform();
        Error=FMath::Max(Error,FMath::Abs(FVector::Distance(World.InverseTransformPosition(A),World.InverseTransformPosition(B))-L->UpperLength));
        Error=FMath::Max(Error,FMath::Abs(FVector::Distance(World.InverseTransformPosition(B),World.InverseTransformPosition(C))-L->LowerLength));
    }
    return Error;
}
