#include "EnvironmentRenderProfileLease.h"

namespace EnvironmentRenderProfilePrivate
{
namespace
{
EConsoleVariableFlags Priority(const IConsoleVariable& Variable)
{
    return static_cast<EConsoleVariableFlags>(Variable.GetFlags() & ECVF_SetByMask);
}

FString ExactFloat(float Value)
{
    // IConsoleVariable::GetString() and Set(float) both use six-digit %g.
    return FString::Printf(TEXT("%.9g"), static_cast<double>(Value));
}

void WriteAtCurrentPriority(IConsoleVariable& Variable, float Value)
{
    const FString Text = ExactFloat(Value);
    if (Priority(Variable) == ECVF_SetByConstructor)
    {
        // UE 5.8 ResolveContext deliberately excludes Constructor from its
        // implicit ReplaceCurrent search and returns SETBY_ERROR. Its supported
        // path for this baseline is an explicit Set at Constructor priority.
        Variable.Set(*Text, ECVF_SetByConstructor);
    }
    else
    {
        Variable.ReplaceCurrentPriorityAndTag(*Text);
    }
}
}

FConsoleFloatLease::~FConsoleFloatLease()
{
    ReleaseAll();
}

bool FConsoleFloatLease::Set(const void* Owner, float Value)
{
    check(IsInGameThread());
    if (!Owner || !FMath::IsFinite(Value) || Value <= 0.f)
    {
        return false;
    }
    if (Owners.IsEmpty())
    {
        PriorValue = Variable.GetFloat();
        if (!FMath::IsFinite(PriorValue))
        {
            return false;
        }
        LastOwnedValue = PriorValue;
        PriorPriority = Priority(Variable);
        bYieldedToExternalWrite = false;
        // Multicast registration preserves the renderer's own CVar callback.
        ChangedHandle = Variable.OnChangedDelegate().AddRaw(this, &FConsoleFloatLease::OnChanged);
    }
    else
    {
        ObserveExternalWrite();
    }
    Owners.Add(Owner, Value);
    ApplyMaximum();
    return true;
}

void FConsoleFloatLease::ObserveExternalWrite()
{
    // Also detect writes made with the unsafe no-callback CVar API.
    if (Variable.GetFloat() != LastOwnedValue || Priority(Variable) != PriorPriority)
    {
        bYieldedToExternalWrite = true;
    }
}

void FConsoleFloatLease::OnChanged(IConsoleVariable* ChangedVariable)
{
    check(IsInGameThread());
    if (ChangedVariable != &Variable)
    {
        return;
    }
    if (bExpectOwnNotification)
    {
        // Exactly one notification belongs to our Set. A second notification
        // can be a reentrant external Set, even when it writes the same value.
        bExpectOwnNotification = false;
    }
    else
    {
        // Even a same-value console write is explicit external ownership. Do
        // not fight it on another actor's update, unregister or PIE shutdown.
        bYieldedToExternalWrite = true;
    }
}

void FConsoleFloatLease::ApplyMaximum()
{
    if (Owners.IsEmpty() || bYieldedToExternalWrite)
    {
        return;
    }
    float Maximum = 0.f;
    for (const auto& Owner : Owners)
    {
        Maximum = FMath::Max(Maximum, Owner.Value);
    }
    if (Variable.GetFloat() != Maximum)
    {
        TGuardValue<bool> OwnNotification(bExpectOwnNotification, true);
        // Keep both the current priority and history tag. Nine significant
        // digits round-trip a float; Set(float)'s %g only uses six digits.
        WriteAtCurrentPriority(Variable, Maximum);
        if (Variable.GetFloat() != Maximum || Priority(Variable) != PriorPriority)
        {
            // A synchronous external callback may itself have changed it.
            bYieldedToExternalWrite = true;
        }
    }
    LastOwnedValue = Variable.GetFloat();
}

void FConsoleFloatLease::Release(const void* Owner)
{
    check(IsInGameThread());
    if (!Owners.Contains(Owner))
    {
        return;
    }
    ObserveExternalWrite();
    Owners.Remove(Owner);
    if (Owners.IsEmpty())
    {
        Finish();
    }
    else
    {
        ApplyMaximum();
    }
}

void FConsoleFloatLease::ReleaseAll()
{
    if (Owners.IsEmpty())
    {
        return;
    }
    check(IsInGameThread());
    ObserveExternalWrite();
    Owners.Empty();
    Finish();
}

void FConsoleFloatLease::Finish()
{
    Variable.OnChangedDelegate().Remove(ChangedHandle);
    ChangedHandle.Reset();
    if (!bYieldedToExternalWrite)
    {
        // Never reassert an old value after the console/user took ownership.
        // Our callback is removed first, so external restore callbacks can win.
        WriteAtCurrentPriority(Variable, PriorValue);
    }
    PriorValue = 0.f;
    LastOwnedValue = 0.f;
    bYieldedToExternalWrite = false;
}
}
