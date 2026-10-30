#include "GHSStreamingInputComponent.h"
#include "Async/Async.h"
#include "Engine/World.h"
#include "IPixelStreaming2Module.h"
#include "PixelStreaming2InputEnums.h"
#include "Serialization/MemoryReader.h"
#include "TimerManager.h"

bool UGHSStreamingInputComponent::ReadDescriptor(FMemoryReader& Message, FString& Out)
{
    // PS2 UIInteraction is a uint16 character count followed by UTF-16, not UTF-8.
    const int64 Start=Message.Tell();
    if(Message.TotalSize()-Start<2) return false;
    uint16 Length=0; Message<<Length;
    const int64 ByteCount=int64(Length)*int64(sizeof(UTF16CHAR));
    if(Length>16384 || Message.TotalSize()-Message.Tell()<ByteCount) return false;
    TArray<UTF16CHAR> Text; Text.SetNumUninitialized(int32(Length)+1);
    Message.Serialize(Text.GetData(),ByteCount);
    Text[Length]=0;
    if(Message.IsError()) return false;
    Out=FString(Length,StringCast<TCHAR>(Text.GetData(),Length).Get());
    return true;
}

void UGHSStreamingInputComponent::BeginPlay()
{
    Super::BeginPlay();
    BindStreamers();
    // The module or additional streamers can become ready after the world's BeginPlay.
    GetWorld()->GetTimerManager().SetTimer(BindTimer,this,&UGHSStreamingInputComponent::BindStreamers,.5f,true);
}

void UGHSStreamingInputComponent::BindStreamers()
{
    if(!IPixelStreaming2Module::IsAvailable()) return;
    const TWeakObjectPtr<UGHSStreamingInputComponent> WeakThis(this);
    Bindings.RemoveAll([](const FBinding& Binding){return !Binding.Handler.IsValid();});
    IPixelStreaming2Module::Get().ForEachStreamer([this,WeakThis](TSharedPtr<IPixelStreaming2Streamer> Streamer)
    {
        const auto Handler=Streamer->GetInputHandler().Pin();
        if(!Handler || Bindings.ContainsByPredicate([&](const FBinding& B){return B.Handler.Pin()==Handler;})) return;
        const auto Previous=Handler->FindMessageHandler(EPixelStreaming2ToStreamerMessage::UIInteraction);
        Bindings.Add({Handler,Previous});
        Handler->RegisterMessageHandler(EPixelStreaming2ToStreamerMessage::UIInteraction,
            [WeakThis,Previous](FString PlayerId,FMemoryReader Message)
            {
                const int64 Start=Message.Tell();
                FString Descriptor;
                const bool bValid=ReadDescriptor(Message,Descriptor);
                // Preserve the engine's existing Blueprint/custom listeners.
                Message.Seek(Start);
                if(bValid && Previous) Previous(PlayerId,Message);
                if(!bValid) return;
                auto Deliver=[WeakThis,Descriptor]()
                {
                    if(auto* Self=WeakThis.Get(); Self && Self->HasBegunPlay()) Self->OnInputEvent.Broadcast(Descriptor);
                };
                if(IsInGameThread()) Deliver();
                else AsyncTask(ENamedThreads::GameThread,MoveTemp(Deliver));
            });
    });
}

void UGHSStreamingInputComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if(GetWorld()) GetWorld()->GetTimerManager().ClearTimer(BindTimer);
    for(const auto& Binding:Bindings)
        if(const auto Handler=Binding.Handler.Pin()) Handler->RegisterMessageHandler(EPixelStreaming2ToStreamerMessage::UIInteraction,Binding.Previous);
    Bindings.Reset();
    Super::EndPlay(Reason);
}

void UGHSStreamingInputComponent::SendPixelStreamingResponse(const FString& Descriptor)
{
    if(!IPixelStreaming2Module::IsAvailable()) return;
    IPixelStreaming2Module::Get().ForEachStreamer([&Descriptor](TSharedPtr<IPixelStreaming2Streamer> Streamer)
    { Streamer->SendAllPlayersMessage(EPixelStreaming2FromStreamerMessage::Response,Descriptor); });
}
