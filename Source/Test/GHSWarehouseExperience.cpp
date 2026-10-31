#include "GHSWarehouseExperience.h"
#include "GHSWarehousePlayerController.h"
#include "GHSTwinHUDWidget.h"
#include "GHSWarehouseCameraPawn.h"
#include "Camera/CameraComponent.h"

namespace
{
class FGenericExperience final:public IGHSWarehouseExperience
{
public:
    explicit FGenericExperience(const FGHSGlobeWarehouse& W):Definition(W){}
    void Enter(AGHSWarehousePlayerController& C,FVector2D Viewport)override
    {
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn()))
        {
            Camera->WarehouseCamera->FieldOfView=GetDefault<AGHSWarehouseCameraPawn>()->WarehouseCamera->FieldOfView;
            Camera->MinimumPitch=-80;Camera->MaximumPitch=-15;Camera->MinimumZoom=900;Camera->MaximumZoom=95000;Camera->MinimumCameraHeight=150;
            Camera->OverviewCenter=Definition.EntryPivot;Camera->OverviewDistance=Definition.EntryDistance;
            Camera->OverviewPitch=Definition.EntryRotation.Pitch;Camera->OverviewYaw=Definition.EntryRotation.Yaw;
            Camera->FocusOnTarget(Definition.EntryPivot,Definition.EntryDistance,Definition.EntryRotation,Viewport,Viewport*.5,0);
        }
    }
    bool IsReady(const AGHSWarehousePlayerController&)const override{return true;}
    void Exit(AGHSWarehousePlayerController&)override{}
    bool UsesWarehouseHUD()const override{return false;}
private:
    FGHSGlobeWarehouse Definition;
};
class FGHSExperience final:public IGHSWarehouseExperience
{
public:
    explicit FGHSExperience(bool bInTraffic):bTraffic(bInTraffic){}
    void Enter(AGHSWarehousePlayerController& C,FVector2D)override
    {
        if(auto* Camera=Cast<AGHSWarehouseCameraPawn>(C.GetPawn()))
        {
            const auto* Default=GetDefault<AGHSWarehouseCameraPawn>();
            Camera->WarehouseCamera->FieldOfView=Default->WarehouseCamera->FieldOfView;
            Camera->MinimumPitch=Default->MinimumPitch;Camera->MaximumPitch=Default->MaximumPitch;Camera->MinimumZoom=Default->MinimumZoom;Camera->MaximumZoom=Default->MaximumZoom;Camera->MinimumCameraHeight=Default->MinimumCameraHeight;
            Camera->OverviewCenter=Default->OverviewCenter;Camera->OverviewDistance=Default->OverviewDistance;Camera->OverviewPitch=Default->OverviewPitch;Camera->OverviewYaw=Default->OverviewYaw;
            Camera->ResetOverview(true);
        }
        C.InitializeWarehouseExperience(bTraffic);
    }
    bool IsReady(const AGHSWarehousePlayerController& C)const override{return C.TwinHUDWidget&&C.TwinHUDWidget->bBrowserReady;}
    void Exit(AGHSWarehousePlayerController& C)override{C.ShutdownWarehouseExperience();}
    bool UsesWarehouseHUD()const override{return true;}
private:
    bool bTraffic;
};
}
TUniquePtr<IGHSWarehouseExperience> IGHSWarehouseExperience::Create(const FGHSGlobeWarehouse& W)
{
    if(W.RuntimeProfile==TEXT("generic")&&W.Features.IsEmpty())return MakeUnique<FGenericExperience>(W);
    if(W.RuntimeProfile==TEXT("ghs")&&W.Features.Contains(TEXT("warehouse-ui")))return MakeUnique<FGHSExperience>(W.Features.Contains(TEXT("traffic")));
    return nullptr;
}
