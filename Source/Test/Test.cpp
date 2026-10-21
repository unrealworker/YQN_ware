// Copyright Epic Games, Inc. All Rights Reserved.

#include "Test.h"
#include "Modules/ModuleManager.h"
#include "GHSTwinPerformance.h"
#include "GHSStreamingRuntime.h"

class FTestGameModule : public FDefaultGameModuleImpl
{
    virtual void StartupModule() override { GHSTwinPerformance::Startup(); GHSStreamingRuntime::Startup(); }
    virtual void ShutdownModule() override { GHSStreamingRuntime::Shutdown(); GHSTwinPerformance::Shutdown(); }
};
IMPLEMENT_PRIMARY_GAME_MODULE( FTestGameModule, Test, "Test" );
