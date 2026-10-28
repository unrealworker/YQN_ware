// Copyright Epic Games, Inc. All Rights Reserved.

#include "VideoSourceGroup.h"
#include "VideoSource.h"
#include "Settings.h"
#include "GHSPixelStreamingPolicy.h"
#include "PixelStreamingPrivate.h"
#include "PixelStreamingTrace.h"
#include "Stats.h"

namespace UE::PixelStreaming
{
	TSharedPtr<FVideoSourceGroup> FVideoSourceGroup::Create()
	{
		return TSharedPtr<FVideoSourceGroup>(new FVideoSourceGroup());
	}

	FVideoSourceGroup::FVideoSourceGroup()
		: bCoupleFramerate(GHS::ShouldCouple(Settings::CVarPixelStreamingWebRTCFps.GetValueOnAnyThread(), Settings::IsCoupledFramerate(), Settings::CVarPixelStreamingCaptureUseFence.GetValueOnAnyThread()))
		, bRequestedCoupleFramerate(Settings::IsCoupledFramerate())
		, FramesPerSecond(FMath::Max(0, Settings::CVarPixelStreamingWebRTCFps.GetValueOnAnyThread()))
	{
	}

	FVideoSourceGroup::~FVideoSourceGroup()
	{
		Stop();
	}

	void FVideoSourceGroup::SetVideoInput(TSharedPtr<FPixelStreamingVideoInput> InVideoInput)
	{
		if (VideoInput)
		{
			VideoInput->OnFrameCaptured.Remove(FrameDelegateHandle);
		}

		VideoInput = InVideoInput;

		if (VideoInput)
		{
			FrameDelegateHandle = VideoInput->OnFrameCaptured.AddSP(AsShared(), &FVideoSourceGroup::OnFrameCaptured);
		}
	}

	void FVideoSourceGroup::SetFPS(int32 InFramesPerSecond)
	{
		FramesPerSecond = FMath::Max(0, InFramesPerSecond);
		SetCoupleFramerate(bRequestedCoupleFramerate.load());
	}

	int32 FVideoSourceGroup::GetFPS()
	{
		return FramesPerSecond.load();
	}

	void FVideoSourceGroup::SetCoupleFramerate(bool Couple)
	{
		bRequestedCoupleFramerate = Couple;
		bCoupleFramerate = GHS::ShouldCouple(FramesPerSecond.load(), Couple, Settings::CVarPixelStreamingCaptureUseFence.GetValueOnAnyThread());
		if (bCoupleFramerate)
		{
			StopThread();
		}
		else
		{
			CheckStartStopThread();
		}
	}

	rtc::scoped_refptr<webrtc::VideoTrackSourceInterface> FVideoSourceGroup::CreateVideoSource(const TFunction<bool()>& InShouldGenerateFramesCheck)
	{
#if WEBRTC_5414
		rtc::scoped_refptr<FVideoSource> NewVideoSource = rtc::scoped_refptr<FVideoSource>(new FVideoSource(VideoInput, InShouldGenerateFramesCheck));
#else
		rtc::scoped_refptr<FVideoSource> NewVideoSource = new FVideoSource(VideoInput, InShouldGenerateFramesCheck);
#endif
		{
			FScopeLock Lock(&CriticalSection);
			VideoSources.Add(NewVideoSource);
		}
		CheckStartStopThread();
		return NewVideoSource;
	}

	void FVideoSourceGroup::RemoveVideoSource(const webrtc::VideoTrackSourceInterface* ToRemove)
	{
		{
			FScopeLock Lock(&CriticalSection);
			VideoSources.RemoveAll([ToRemove](const rtc::scoped_refptr<FVideoSource>& Target) {
				return Target.get() == ToRemove;
			});
		}
		CheckStartStopThread();
	}

	void FVideoSourceGroup::RemoveAllVideoSources()
	{
		{
			FScopeLock Lock(&CriticalSection);
			VideoSources.Empty();
		}
		CheckStartStopThread();
	}

	void FVideoSourceGroup::Start()
	{
		if (!bRunning.exchange(true))
		{
			CheckStartStopThread();
		}
	}

	void FVideoSourceGroup::Stop()
	{
		bRunning = false;
		StopThread();
	}

	void FVideoSourceGroup::Tick()
	{
	    TRACE_CPUPROFILER_EVENT_SCOPE_ON_CHANNEL_STR("PixelStreaming Video Source Group Tick", PixelStreamingChannel);
		FScopeLock Lock(&CriticalSection);
		// for each player session, push a frame
		for (auto& VideoSource : VideoSources)
		{
			if (VideoSource)
			{
				VideoSource->MaybePushFrame();
			}
		}
	}

	void FVideoSourceGroup::OnFrameCaptured()
	{
		if (bCoupleFramerate)
		{
			Tick();
		}
		else
		{
			// We are in decoupled render/streaming mode - we should wake our VideoSourceGroup::FFrameThread (if it is sleeping)
			FScopeLock FrameLock(&FrameThreadGuard);
			if(FrameRunnable && FrameRunnable->FrameEvent.Get())
			{
				FrameRunnable->FrameEvent.Get()->Trigger();
			}
		}
	}

	void FVideoSourceGroup::StartThread()
	{
		FScopeLock LifecycleLock(&FrameThreadLifecycleGuard);
		FScopeLock FrameLock(&FrameThreadGuard);
		if (bRunning && !bCoupleFramerate && !bThreadRunning)
		{
			FrameRunnable = MakeUnique<FFrameThread>(AsWeak());
			FrameThread = FRunnableThread::Create(FrameRunnable.Get(), TEXT("FVideoSourceGroup Thread"), 0, TPri_TimeCritical);
			bThreadRunning = FrameThread != nullptr;
		}
	}

	void FVideoSourceGroup::StopThread()
	{
		FScopeLock LifecycleLock(&FrameThreadLifecycleGuard);
		FRunnableThread* ThreadToJoin = nullptr;
		TUniquePtr<FFrameThread> RunnableToStop;
		{
			FScopeLock FrameLock(&FrameThreadGuard);
			// Detach while capture callbacks are excluded. Keep the runnable
			// alive locally until its worker is fully stopped, then destroy it.
			ThreadToJoin = FrameThread;
			FrameThread = nullptr;
			RunnableToStop = MoveTemp(FrameRunnable);
			bThreadRunning = false;
			if (RunnableToStop)
			{
				RunnableToStop->Stop();
			}
		}
		if (ThreadToJoin != nullptr)
		{
			// The frame pointer lock and Tick's CriticalSection are NOT held
			// while joining. A worker already in Tick can finish normally.
			ThreadToJoin->Kill(true);
			delete ThreadToJoin;
		}
	}

	void FVideoSourceGroup::CheckStartStopThread()
	{
		if (bRunning)
		{
			int32 NumSources;
			{
				FScopeLock Lock(&CriticalSection);
				NumSources = VideoSources.Num();
			}
			if (bThreadRunning && NumSources == 0)
			{
				StopThread();
			}
			else if (!bThreadRunning && NumSources > 0)
			{
				StartThread();
			}
		}
	}

	bool FVideoSourceGroup::FFrameThread::Init()
	{
		bIsRunning = true;
		return true;
	}

	uint32 FVideoSourceGroup::FFrameThread::Run()
	{
		while (bIsRunning)
		{
			if(TSharedPtr<FVideoSourceGroup> VideoSourceGroup = OuterVideoSourceGroup.Pin())
			{
				const int32 TargetFPS = VideoSourceGroup->FramesPerSecond.load();
				if (GHS::IsUncapped(TargetFPS) || VideoSourceGroup->bCoupleFramerate)
				{
					// Only capture callbacks submit in uncapped mode. Guard a mode
					// switch before this worker has been joined as well.
					FrameEvent.Get()->Wait(10);
					continue;
				}
				const double TimeSinceLastSubmitMs = FPlatformTime::ToMilliseconds64(FPlatformTime::Cycles64() - LastSubmitCycles);

				// Decrease this value to make expected frame delivery more precise, however may result in more old frames being sent
				const double PrecisionFactor = 0.1;
				const double WaitFactor = UE::PixelStreaming::Settings::CVarPixelStreamingDecoupleWaitFactor.GetValueOnAnyThread();

				// In "auto" mode vary this value based on historical average
				const double TargetSubmitMs = 1000.0 / TargetFPS;
				const double TargetSubmitMsWithPadding = TargetSubmitMs * WaitFactor;
				const double CloseEnoughMs = TargetSubmitMs * PrecisionFactor;
				const bool bFrameOverdue = TimeSinceLastSubmitMs >= TargetSubmitMsWithPadding;

				// Check frame arrived in time
				if(!bFrameOverdue)
				{
					// Frame arrived in a timely fashion, but is it too soon to maintain our target rate? If so, sleep.
					double WaitTimeRemainingMs = TargetSubmitMsWithPadding - TimeSinceLastSubmitMs;
					if(WaitTimeRemainingMs > CloseEnoughMs)
					{
						bool bGotNewFrame = FrameEvent.Get()->Wait(WaitTimeRemainingMs);
						if(!bGotNewFrame)
						{
							UE_LOG(LogPixelStreaming, VeryVerbose, TEXT("Old frame submitted"));
						}
					}
				}

				// Push frame immediately
				if (bIsRunning && !VideoSourceGroup->bCoupleFramerate && !GHS::IsUncapped(VideoSourceGroup->FramesPerSecond.load()))
				{
					PushFrame(VideoSourceGroup);
				}

			}
		}
		return 0;
	}

	void FVideoSourceGroup::FFrameThread::Stop()
	{
		bIsRunning = false;
		FrameEvent.Get()->Trigger();
	}

	void FVideoSourceGroup::FFrameThread::Exit()
	{
		bIsRunning = false;
	}

	/*
	* Note this function is required as part of `FSingleThreadRunnable` and only gets called when engine is run in single-threaded mode, 
	* so the logic is much less complex as this is not a case we particularly optimize for, a simple tick on an interval will be acceptable.
	*/
	void FVideoSourceGroup::FFrameThread::Tick()
	{
		if(TSharedPtr<FVideoSourceGroup> VideoSourceGroup = OuterVideoSourceGroup.Pin())
		{
			const int32 TargetFPS = VideoSourceGroup->FramesPerSecond.load();
			if (!bIsRunning || GHS::IsUncapped(TargetFPS) || VideoSourceGroup->bCoupleFramerate)
			{
				return;
			}
			const uint64 NowCycles = FPlatformTime::Cycles64();
			const double DeltaMs = FPlatformTime::ToMilliseconds64(NowCycles - LastSubmitCycles);
			const double TargetSubmitMs = 1000.0 / TargetFPS;
			if (DeltaMs >= TargetSubmitMs)
			{
				PushFrame(VideoSourceGroup);
			}
		}
	}

	void FVideoSourceGroup::FFrameThread::PushFrame(TSharedPtr<FVideoSourceGroup> VideoSourceGroup)
	{
		VideoSourceGroup->Tick();
		LastSubmitCycles = FPlatformTime::Cycles64();
	}
} // namespace UE::PixelStreaming
