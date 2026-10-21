#include "GHSDisplayStartup.h"
#include "Modules/ModuleManager.h"

// Keep the gameplay module at Default. This module owns only the pre-window policy.
class FGHSDisplayBootstrapModule : public IModuleInterface
{
    virtual void StartupModule() override { GHSDisplayStartup::Startup(); }
    virtual void ShutdownModule() override { GHSDisplayStartup::Shutdown(); }
};

IMPLEMENT_MODULE(FGHSDisplayBootstrapModule,GHSDisplayBootstrap)
