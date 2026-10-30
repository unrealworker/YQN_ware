#pragma once

#include "Misc/AutomationTest.h"

namespace GHSAutomationTests
{
// Keep the original UE 5.4 contexts. UE 5.8's global application mask also
// includes ProgramContext, which these game/editor tests did not opt into.
// auto supports both the old integer flags and the new scoped enum flags.
inline constexpr auto ApplicationContextMask = EAutomationTestFlags::EditorContext
    | EAutomationTestFlags::ClientContext
    | EAutomationTestFlags::ServerContext
    | EAutomationTestFlags::CommandletContext;
}
