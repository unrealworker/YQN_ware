#pragma once

#include "CoreMinimal.h"
#include "HAL/IConsoleManager.h"

namespace EnvironmentRenderProfilePrivate
{
/** Game-thread-only shared ownership of one float CVar. Does not own the CVar. */
class FConsoleFloatLease final
{
public:
    explicit FConsoleFloatLease(IConsoleVariable& InVariable) : Variable(InVariable) {}
    ~FConsoleFloatLease();
    FConsoleFloatLease(const FConsoleFloatLease&) = delete;
    FConsoleFloatLease& operator=(const FConsoleFloatLease&) = delete;

    // Owner is only an identity token; no UObject is retained or dereferenced.
    bool Set(const void* Owner, float Value);
    void Release(const void* Owner);
    void ReleaseAll();

private:
    void ObserveExternalWrite();
    void ApplyMaximum();
    void Finish();
    void OnChanged(IConsoleVariable* ChangedVariable);

    IConsoleVariable& Variable;
    TMap<const void*, float> Owners;
    FDelegateHandle ChangedHandle;
    float PriorValue = 0.f;
    float LastOwnedValue = 0.f;
    EConsoleVariableFlags PriorPriority = ECVF_SetByConstructor;
    bool bExpectOwnNotification = false;
    bool bYieldedToExternalWrite = false;
};
}
