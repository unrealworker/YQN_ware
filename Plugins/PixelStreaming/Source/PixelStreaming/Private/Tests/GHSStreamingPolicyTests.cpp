#include "Misc/AutomationTest.h"
#include "GHSPixelStreamingPolicy.h"
#include "WebRTCIncludes.h"
#include "VideoSourceGroup.h"
#include "Settings.h"
#include "PixelStreamingVideoInputI420.h"
#include "Async/Async.h"

#if WITH_DEV_AUTOMATION_TESTS
namespace UE::PixelStreaming
{
	IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStreamingPolicyTest,
		"GHS.PixelStreaming.UncappedPolicy",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)

	bool FGHSStreamingPolicyTest::RunTest(const FString& Parameters)
	{
		// Exercise the real WebRTC optional field, including removal of an old cap.
		webrtc::RtpEncodingParameters Encoding;
		GHS::SetEncodingFrameLimit(Encoding, 60);
		TestTrue(TEXT("Positive FPS remains an explicit limit"), Encoding.max_framerate.has_value() && Encoding.max_framerate.value() == 60.0);
		GHS::SetEncodingFrameLimit(Encoding, 0);
		TestFalse(TEXT("Zero removes max_framerate rather than setting zero"), Encoding.max_framerate.has_value());
		GHS::SetEncodingFrameLimit(Encoding, 144);
		TestEqual(TEXT("Can return to an explicit rate"), Encoding.max_framerate.value(), 144.0);
		TestTrue(TEXT("Uncapped mode forces capture coupling even with a fence"), GHS::ShouldCouple(0, false, true));
		TestFalse(TEXT("Positive FPS can still use a decoupled worker"), GHS::ShouldCouple(60, false, true));

		TSharedPtr<FVideoSourceGroup> Group = FVideoSourceGroup::Create();
		Group->SetFPS(0);
		Group->SetCoupleFramerate(false);
		TestEqual(TEXT("Capture group retains uncapped sentinel"), Group->GetFPS(), 0);
		Group->SetFPS(-1);
		TestEqual(TEXT("Negative input is normalized safely"), Group->GetFPS(), 0);
		Group->SetFPS(60);
		TestEqual(TEXT("Capture group accepts a subsequent positive FPS"), Group->GetFPS(), 60);

		GHS::FMeasuredRateHint Hint;
		Hint.Reset(0);
		TestTrue(TEXT("Initial hardware hint is positive"), Hint.Get() > 0);
		for (int64 Index = 0; Index <= 120; ++Index)
		{
			Hint.AddFrame(Index * 1000000 / 120);
		}
		TestEqual(TEXT("Measured hint can rise beyond a 60 FPS initial value"), Hint.Get(), uint32(120));
		Hint.AddFrame(1);
		TestEqual(TEXT("Old timestamps leave the valid hint intact"), Hint.Get(), uint32(120));

		webrtc::EncodedImage Image;
		TestEqual(TEXT("Upstream playout default is preserved until explicitly enabled"), Image.playout_delay_.min_ms, -1);
		Image.playout_delay_ = webrtc::VideoPlayoutDelay(0, 0);
		TestEqual(TEXT("Low-latency RTP minimum is zero"), Image.playout_delay_.min_ms, 0);
		TestEqual(TEXT("Low-latency RTP maximum is zero"), Image.playout_delay_.max_ms, 0);
		return true;
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSStreamingCaptureSwitchTest,
		"GHS.PixelStreaming.ConcurrentCaptureModeSwitch",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)

	bool FGHSStreamingCaptureSwitchTest::RunTest(const FString& Parameters)
	{
		IConsoleVariable* Fence = Settings::CVarPixelStreamingCaptureUseFence.AsVariable();
		const bool PreviousFence = Fence->GetBool();
		const EConsoleVariableFlags PreviousSetBy = static_cast<EConsoleVariableFlags>(Fence->GetFlags() & ECVF_SetByMask);
		Fence->Set(true, ECVF_SetByConsole);

		TSharedPtr<FVideoSourceGroup> Group = FVideoSourceGroup::Create();
		TSharedPtr<FPixelStreamingVideoInputI420> Input = MakeShared<FPixelStreamingVideoInputI420>();
		Group->SetVideoInput(Input);
		auto Source = Group->CreateVideoSource([] { return false; });
		Group->SetFPS(120);
		Group->SetCoupleFramerate(false);
		Group->Start();
		std::atomic<bool> Capturing{true};
		std::atomic<uint32> Captures{0};
		TFuture<void> CaptureTask = Async(EAsyncExecution::Thread, [Input, &Capturing, &Captures] {
			while (Capturing)
			{
				Input->OnFrameCaptured.Broadcast();
				++Captures;
				FPlatformProcess::SleepNoStats(0.0001f);
			}
		});
		for (int32 Index = 0; Index < 200; ++Index)
		{
			Group->SetFPS(0);
			Group->SetFPS(120);
			Group->SetCoupleFramerate(false);
		}
		Group->Stop();
		Capturing = false;
		CaptureTask.Wait();
		Group->RemoveVideoSource(Source.get());
		Group->SetVideoInput(nullptr);
		Fence->ClearFlags(ECVF_SetByMask);
		Fence->Set(PreviousFence, PreviousSetBy);
		TestTrue(TEXT("Capture callbacks overlapped mode switches without invalid event access"), Captures.load() > 0);
		TestFalse(TEXT("Capture group stopped after the stress test"), Group->IsThreadRunning());
		return true;
	}
}
#endif
