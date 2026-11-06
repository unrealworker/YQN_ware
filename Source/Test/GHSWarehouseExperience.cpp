#include "GHSWarehouseExperience.h"
#include "GHSWarehousePlayerController.h"
#include "GHSTwinHUDWidget.h"
#include "GHSWarehouseCameraPawn.h"
#include "Camera/CameraComponent.h"

namespace
{
struct FArrival
{
    FVector2D Viewport=FVector2D(1920,1080);
    float Elapsed=0,Duration=1.6f;
    FGHSCameraReplayPose FinalPose;
    bool bRestoreOverview=false;
    void Begin(AGHSWarehousePlayerController& C,bool bReduced)
    {
        Elapsed=0;Duration=bReduced?0.f:1.6f;bRestoreOverview=false;
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn());Camera&&Duration>0)
        {
            const auto Final=Camera->CaptureReplayPose();
            FinalPose=Final;bRestoreOverview=Final.OverviewFraming;
            auto High=Final;High.Distance=FMath::Min(Camera->MaximumZoom,Final.Distance*1.35f);
            High.Rotation.Pitch=FMath::Max(-75.,Final.Rotation.Pitch-22.);
            High.SocketOffset=Final.FramingRatio*High.Distance;
            High.OverviewFraming=false;
            Camera->RestoreReplayPose(High);
            const double Focal=Viewport.X/(2*FMath::Tan(FMath::DegreesToRadians(Camera->WarehouseCamera->FieldOfView*.5)));
            const FVector2D Framing(Viewport.X*.5-Final.FramingRatio.Y*Focal,Viewport.Y*.5+Final.FramingRatio.Z*Focal);
            Camera->TransitionToPose(Final.Pivot,Final.Distance,Final.Rotation,Viewport,Framing,!Final.ObjectPivot,Duration);
        }
    }
    bool Tick(AGHSWarehousePlayerController& C,float Dt)
    {
        Elapsed+=Dt;
        if(C.TwinHUDWidget)C.TwinHUDWidget->SetRenderOpacity(Duration==0?1.f:FMath::SmoothStep(.18f,.9f,Elapsed));
        auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn());
        const bool Finished=Elapsed>=Duration&&(!Camera||!Camera->IsPoseTransitionActive());
        if(Finished&&Camera&&bRestoreOverview)
        {
            const auto Current=Camera->CaptureReplayPose();
            if(Current.Pivot.Equals(FinalPose.Pivot,.1)&&Current.Rotation.Equals(FinalPose.Rotation,.01)
                &&FMath::IsNearlyEqual(Current.Distance,FinalPose.Distance,.1f))Camera->RestoreReplayPose(FinalPose);
            bRestoreOverview=false;
        }
        return Finished;
    }
};
class FGenericExperience final:public IGHSWarehouseExperience
{
public:
    explicit FGenericExperience(const FGHSGlobeWarehouse& W):Definition(W){}
    void Enter(AGHSWarehousePlayerController& C,FVector2D Viewport)override
    {
        Arrival.Viewport=Viewport;
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn()))
        {
            Camera->SetObjectOrbitNavigationEnabled(false);
            const auto* Default=GetDefault<AGHSWarehouseCameraPawn>();
            Camera->WarehouseCamera->FieldOfView=Default->WarehouseCamera->FieldOfView;
            Camera->OrbitDegreesPerPixel=Default->OrbitDegreesPerPixel;Camera->PitchDegreesPerPixel=Default->PitchDegreesPerPixel;
            Camera->WheelZoomExponent=Default->WheelZoomExponent;Camera->MaximumPan=Default->MaximumPan;
            Camera->RotationLagSpeed=Default->RotationLagSpeed;Camera->MovementLagSpeed=Default->MovementLagSpeed;Camera->ZoomLagSpeed=Default->ZoomLagSpeed;
            Camera->MinimumPitch=-80;Camera->MaximumPitch=-15;Camera->MinimumZoom=900;Camera->MaximumZoom=95000;Camera->MinimumCameraHeight=150;
            Camera->OverviewCenter=Definition.EntryPivot;Camera->OverviewDistance=Definition.EntryDistance;
            Camera->OverviewPitch=Definition.EntryRotation.Pitch;Camera->OverviewYaw=Definition.EntryRotation.Yaw;
            if(UsesWarehouseHUD()) Camera->FrameOverview(Viewport,FVector2D::ZeroVector,Viewport,0);
            else Camera->FocusOnTarget(Definition.EntryPivot,Definition.EntryDistance,Definition.EntryRotation,Viewport,Viewport*.5,0);
        }
        if(UsesWarehouseHUD())
        {
            FString Brand=Definition.Name;Definition.Name.Split(TEXT(" · "),&Brand,nullptr);
            C.InitializeWarehouseExperience(false,true,Brand+TEXT(" · 主仓储"));
        }
    }
    bool IsReady(const AGHSWarehousePlayerController& C)const override{return !UsesWarehouseHUD()||(C.TwinHUDWidget&&C.TwinHUDWidget->IsInitialViewReady());}
    void BeginArrival(AGHSWarehousePlayerController& C,bool Reduced)override{Arrival.Begin(C,Reduced);}
    bool TickArrival(AGHSWarehousePlayerController& C,float Dt)override{return Arrival.Tick(C,Dt);}
    void Exit(AGHSWarehousePlayerController& C)override{if(UsesWarehouseHUD())C.ShutdownWarehouseExperience();}
    bool UsesWarehouseHUD()const override{return Definition.Features.Contains(TEXT("roof-inspection"));}
private:
    FGHSGlobeWarehouse Definition;
    FArrival Arrival;
};
class FGHSExperience final:public IGHSWarehouseExperience
{
public:
    explicit FGHSExperience(bool bInTraffic):bTraffic(bInTraffic){}
    void Enter(AGHSWarehousePlayerController& C,FVector2D Viewport)override
    {
        Arrival.Viewport=Viewport;
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn()))
        {
            Camera->SetObjectOrbitNavigationEnabled(false);
            const auto* Default=GetDefault<AGHSWarehouseCameraPawn>();
            Camera->WarehouseCamera->FieldOfView=Default->WarehouseCamera->FieldOfView;
            Camera->MinimumPitch=Default->MinimumPitch;Camera->MaximumPitch=Default->MaximumPitch;Camera->MinimumZoom=Default->MinimumZoom;Camera->MaximumZoom=Default->MaximumZoom;Camera->MinimumCameraHeight=Default->MinimumCameraHeight;
            Camera->OverviewCenter=Default->OverviewCenter;Camera->OverviewDistance=Default->OverviewDistance;Camera->OverviewPitch=Default->OverviewPitch;Camera->OverviewYaw=Default->OverviewYaw;
            Camera->ResetOverview(true);
        }
        C.InitializeWarehouseExperience(bTraffic);
        if(C.TwinHUDWidget)C.TwinHUDWidget->SetRenderOpacity(0);
    }
    bool IsReady(const AGHSWarehousePlayerController& C)const override{return C.TwinHUDWidget&&C.TwinHUDWidget->IsInitialViewReady();}
    void BeginArrival(AGHSWarehousePlayerController& C,bool Reduced)override{Arrival.Begin(C,Reduced);}
    bool TickArrival(AGHSWarehousePlayerController& C,float Dt)override{return Arrival.Tick(C,Dt);}
    void Exit(AGHSWarehousePlayerController& C)override{C.ShutdownWarehouseExperience();}
    bool UsesWarehouseHUD()const override{return true;}
private:
    bool bTraffic;
    FArrival Arrival;
};
}
TUniquePtr<IGHSWarehouseExperience> IGHSWarehouseExperience::Create(const FGHSGlobeWarehouse& W)
{
    if(W.RuntimeProfile==TEXT("generic")&&(W.Features.IsEmpty()||(W.Features.Num()==1&&W.Features.Contains(TEXT("roof-inspection")))))return MakeUnique<FGenericExperience>(W);
    if(W.RuntimeProfile==TEXT("ghs")&&W.Features.Contains(TEXT("warehouse-ui")))return MakeUnique<FGHSExperience>(W.Features.Contains(TEXT("traffic")));
    return nullptr;
}
