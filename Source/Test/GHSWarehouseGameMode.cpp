#include "GHSWarehouseGameMode.h"
#include "GHSWarehouseCameraPawn.h"
#include "GHSWarehousePlayerController.h"

AGHSWarehouseGameMode::AGHSWarehouseGameMode()
{
    DefaultPawnClass = AGHSWarehouseCameraPawn::StaticClass();
    PlayerControllerClass = AGHSWarehousePlayerController::StaticClass();
    HUDClass = nullptr;
}
