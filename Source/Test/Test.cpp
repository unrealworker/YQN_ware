// Copyright Epic Games, Inc. All Rights Reserved.

#include "Test.h"
#include "Modules/ModuleManager.h"
#include "GHSTwinPerformance.h"

class FTestGameModule : public FDefaultGameModuleImpl
{
    virtual void StartupModule() override { GHSTwinPerformance::Startup(); }
    virtual void ShutdownModule() override { GHSTwinPerformance::Shutdown(); }
};
IMPLEMENT_PRIMARY_GAME_MODULE( FTestGameModule, Test, "Test" );
