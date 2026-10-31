#pragma once
#include "CoreMinimal.h"
#include "GHSWarehouseRegistry.h"
class AGHSWarehousePlayerController;

/** Destination behavior lives outside the globe, keeping profile-specific features isolated. */
class TEST_API IGHSWarehouseExperience
{
public:
    virtual ~IGHSWarehouseExperience()=default;
    virtual void Enter(AGHSWarehousePlayerController& Controller,FVector2D Viewport)=0;
    virtual bool IsReady(const AGHSWarehousePlayerController& Controller)const=0;
    /** Starts only after the destination HUD has established its real viewport framing. */
    virtual void BeginArrival(AGHSWarehousePlayerController& Controller,bool bReducedMotion)=0;
    virtual bool TickArrival(AGHSWarehousePlayerController& Controller,float DeltaSeconds)=0;
    virtual void Exit(AGHSWarehousePlayerController& Controller)=0;
    virtual bool UsesWarehouseHUD()const=0;
    static TUniquePtr<IGHSWarehouseExperience> Create(const FGHSGlobeWarehouse& Warehouse);
};
