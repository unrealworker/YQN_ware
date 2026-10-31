#pragma once
#include "CoreMinimal.h"
#include "GHSWarehouseCameraPawn.h"

/** Camera-space continuous approach along a great circle; never cuts through the planet. */
struct FGHSGlobeFlight
{
    static constexpr float Duration=2.8f;
    static float Ease(float T){T=FMath::Clamp(T,0.f,1.f);return T*T*T*(10+T*(-15+6*T));}
    static FVector Eye(const FGHSCameraReplayPose& P)
    {return P.Pivot+P.TargetOffset+P.Rotation.RotateVector(P.SocketOffset-FVector(P.Distance,0,0));}
    void Begin(const FGHSCameraReplayPose& Pose,FVector InCenter,float InRadius,FVector Destination)
    {
        Start=Pose;Center=InCenter;Radius=InRadius;Target=Destination;
        const FVector Offset=Eye(Start)-Center;
        StartRadius=Offset.Size();StartNormal=Offset.GetSafeNormal();
        Arc=FQuat::FindBetweenNormals(StartNormal,(Target-Center).GetSafeNormal());
    }
    FGHSCameraReplayPose Sample(float T)const
    {
        if(T<=0)return Start;
        const float Alpha=Ease(T);
        const FVector Normal=FQuat::Slerp(FQuat::Identity,Arc,Alpha).RotateVector(StartNormal);
        const double StartAltitude=FMath::Max(.001,StartRadius-Radius);
        // Align around the globe before the fast descent. A logarithmic descent
        // magnifies a world atlas into a blurry ground texture halfway through.
        const double Altitude=FMath::Lerp(StartAltitude,double(Radius)*.04,double(Ease(T*T)));
        const FVector Camera=Center+Normal*(Radius+Altitude);
        const FVector Aim=FMath::Lerp(Center,Target,double(Alpha));
        const FQuat Look=(Aim-Camera).Rotation().Quaternion();
        FGHSCameraReplayPose Result=Start;
        Result.Rotation=FQuat::Slerp(Start.Rotation.Quaternion(),Look,Ease(T/.45f)).Rotator();
        Result.Rotation.Roll=0;
        Result.Distance=FMath::Lerp(Start.Distance,Radius*.04f,Alpha);
        Result.SocketOffset=FMath::Lerp(Start.SocketOffset,FVector::ZeroVector,double(Alpha));
        Result.TargetOffset=FMath::Lerp(Start.TargetOffset,FVector::ZeroVector,double(Alpha));
        Result.Pivot=Camera-Result.TargetOffset-Result.Rotation.RotateVector(Result.SocketOffset-FVector(Result.Distance,0,0));
        Result.FocusTarget=Target;Result.ObjectPivot=true;Result.UseFraming=false;Result.OverviewFraming=false;Result.GroundPanRecovery=false;
        return Result;
    }
private:
    FGHSCameraReplayPose Start;
    FVector Center=FVector::ZeroVector,Target=FVector::ZeroVector,StartNormal=FVector::ForwardVector;
    FQuat Arc=FQuat::Identity;
    double StartRadius=1;
    float Radius=1;
};
