#pragma once

/** Explicit opt-in benchmark. Inert unless -TwinPerf=<label> is supplied. */
namespace GHSTwinPerformance
{
    void Startup();
    void Shutdown();
}
