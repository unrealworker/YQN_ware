#pragma once

#include "CoreMinimal.h"
#include "Components/PoseableMeshComponent.h"
#include "MPRWorkerPoseComponent.generated.h"

class UAnimSequence;
class USkeletalMesh;

/** Presentation inputs only. The sorter remains the sole owner of cargo and time. */
struct FMPRWorkerPoseInput
{
    // Feet centre on the floor. +X faces forward, +Y is the worker's right.
    FTransform BodyWorld = FTransform::Identity;
    FVector LeftPalmWorld = FVector::ZeroVector;
    FVector RightPalmWorld = FVector::ZeroVector;
    FVector MoveDirectionWorld = FVector::ForwardVector;
    // Distance along the current movement, not real time or frame count.
    double TravelDistanceCm = 0.;
    double SimulationTime = 0.;
    double GripAlpha = 1.;
    // Ease at the beginning/end of a move to avoid popping into a wide stride.
    double GaitBlend = 1.;
    double TorsoLeanDegrees = 5.;
    bool bWalking = false;
    bool bPushGrip = false;
    bool bVisible = true;
};

/** Official mannequin presentation, driven deterministically by the sorter. */
UCLASS(ClassGroup=(MPR), meta=(BlueprintSpawnableComponent))
class TEST_API UMPRWorkerPoseComponent : public UPoseableMeshComponent
{
    GENERATED_BODY()
public:
    UMPRWorkerPoseComponent();
    bool InitializeWorker(USkeletalMesh* Mesh, UAnimSequence* OptionalIdle = nullptr);
    void ApplyWorkerPose(const FMPRWorkerPoseInput& Input);

    UFUNCTION(BlueprintPure, Category="MPR Worker") bool IsWorkerPoseReady() const { return bPoseReady; }
    UFUNCTION(BlueprintPure, Category="MPR Worker") FVector GetPalmWorld(bool bLeft) const;
    UFUNCTION(BlueprintPure, Category="MPR Worker") FVector GetFootSoleWorld(bool bLeft) const;
    UFUNCTION(BlueprintPure, Category="MPR Worker") double GetPalmContactErrorCm(bool bLeft) const;
    UFUNCTION(BlueprintPure, Category="MPR Worker") double GetMaximumLimbLengthErrorCm() const;
    UFUNCTION(BlueprintPure, Category="MPR Worker") double GetReferenceFacingYawDegrees() const { return ReferenceFacingYawDegrees; }
    UFUNCTION(BlueprintPure, Category="MPR Worker") int32 GetPoseRevision() const { return PoseRevision; }

    // Pure gait function also used by regression tests. X is along travel, Z is lift.
    static FVector FootCycleOffset(double DistanceCm, bool bLeft, bool bWalking, double StrideScale = 1.);

private:
    struct FLimb
    {
        int32 Upper = INDEX_NONE, Lower = INDEX_NONE, End = INDEX_NONE;
        double UpperLength = 0., LowerLength = 0.;
    };
    struct FHand
    {
        FLimb Arm;
        FVector PalmLocal = FVector::ZeroVector;
        FVector FingerDirection = FVector::ForwardVector;
        FVector PalmNormal = FVector::UpVector;
        TArray<int32> Fingers;
        TArray<FVector> CurlAxesLocal;
    };
    void BuildComponentPose();
    void SetComponentBone(int32 Bone, const FTransform& Transform);
    void RotateComponentBone(int32 Bone, const FQuat& Delta);
    void SolveLimb(const FLimb& Limb, const FVector& Target, const FVector& Pole, const FQuat& EndRotation);
    void PoseHand(int32 Side, const FVector& Target, const FVector& Inward, double Grip, bool bPushGrip);

    TArray<FTransform> ReferenceLocal, ReferenceComponent, BaseLocal, WorkingLocal, WorkingComponent;
    TArray<int32> Parents;
    FHand Hands[2];
    FLimb Legs[2];
    int32 ToeBones[2] = {INDEX_NONE, INDEX_NONE};
    FVector SoleLocal[2] = {FVector::ZeroVector, FVector::ZeroVector};
    FVector LastPalmTargets[2] = {FVector::ZeroVector, FVector::ZeroVector};
    FVector ReferenceForward = FVector::ForwardVector;
    FQuat MeshToBody = FQuat::Identity;
    int32 Spine[3] = {INDEX_NONE, INDEX_NONE, INDEX_NONE};
    int32 Pelvis = INDEX_NONE;
    int32 PoseRevision = 0;
    double ReferenceFacingYawDegrees = 0.;
    bool bPoseReady = false;
};
