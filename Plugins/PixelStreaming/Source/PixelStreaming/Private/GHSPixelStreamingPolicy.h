// Project-local policy helpers. No engine or WebRTC dependencies so these can
// be exercised by both standalone C++ tests and Unreal automation tests.
#pragma once

#include <cmath>
#include <cstdint>

namespace UE::PixelStreaming::GHS
{
	constexpr bool IsUncapped(int32_t FPS) { return FPS <= 0; }
	constexpr bool ShouldCouple(int32_t FPS, bool RequestedCoupled, bool UsesFence)
	{
		return IsUncapped(FPS) || RequestedCoupled || !UsesFence;
	}

	template <typename EncodingType>
	void SetEncodingFrameLimit(EncodingType& Encoding, int32_t FPS)
	{
		if (IsUncapped(FPS))
		{
			Encoding.max_framerate.reset();
		}
		else
		{
			Encoding.max_framerate = static_cast<double>(FPS);
		}
	}

	// Hardware codecs require a positive rate-control hint, even when no frame
	// limiter is used. This value is never used to decide whether to send a frame.
	inline uint32_t PositiveRateHint(double FPS, double Fallback = 60.0)
	{
		const double ValidFPS = std::isfinite(FPS) && FPS >= 1.0 ? FPS
			: (std::isfinite(Fallback) && Fallback >= 1.0 ? Fallback : 60.0);
		return static_cast<uint32_t>(std::ceil(ValidFPS));
	}

	class FMeasuredRateHint
	{
	public:
		void Reset(double InitialFPS)
		{
			Rate = PositiveRateHint(InitialFPS);
			WindowStartUs = -1;
			LastTimestampUs = -1;
			Intervals = 0;
		}

		void AddFrame(int64_t TimestampUs)
		{
			if (TimestampUs < 0 || TimestampUs <= LastTimestampUs)
			{
				return;
			}
			LastTimestampUs = TimestampUs;
			if (WindowStartUs < 0)
			{
				WindowStartUs = TimestampUs;
				return;
			}
			++Intervals;
			const int64_t ElapsedUs = TimestampUs - WindowStartUs;
			if (ElapsedUs >= 500000)
			{
				Rate = PositiveRateHint(static_cast<double>(Intervals) * 1000000.0 / ElapsedUs, Rate);
				WindowStartUs = TimestampUs;
				Intervals = 0;
			}
		}

		uint32_t Get() const { return Rate; }

	private:
		uint32_t Rate = 60;
		int64_t WindowStartUs = -1;
		int64_t LastTimestampUs = -1;
		uint32_t Intervals = 0;
	};
}
