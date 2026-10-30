#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "IPixelStreaming2InputHandler.h"
#include "TimerManager.h"
#include "GHSStreamingInputComponent.generated.h"

/** Public PS2 API bridge. Does not depend on the engine's unexported Blueprint input class. */
UCLASS()
class UGHSStreamingInputComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnInput, const FString&, Descriptor);
    UPROPERTY() FOnInput OnInputEvent;
    void SendPixelStreamingResponse(const FString& Descriptor);
    static bool ReadDescriptor(FMemoryReader& Message, FString& Out);
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    struct FBinding
    {
        TWeakPtr<IPixelStreaming2InputHandler> Handler;
        IPixelStreaming2InputHandler::MessageHandlerFn Previous;
    };
    void BindStreamers();
    TArray<FBinding> Bindings;
    FTimerHandle BindTimer;
};
