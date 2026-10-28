#include "GHSPixelStreamingPolicy.h"
#include <cassert>
#include <limits>
#include <optional>
#include <iostream>

using namespace UE::PixelStreaming::GHS;

int main()
{
	struct Encoding { std::optional<double> max_framerate; } Sender;
	SetEncodingFrameLimit(Sender, 60);
	assert(Sender.max_framerate == 60.0);
	SetEncodingFrameLimit(Sender, 0);
	assert(!Sender.max_framerate.has_value());
	SetEncodingFrameLimit(Sender, -1);
	assert(!Sender.max_framerate.has_value());
	SetEncodingFrameLimit(Sender, 144);
	assert(Sender.max_framerate == 144.0);
	SetEncodingFrameLimit(Sender, 0);
	assert(!Sender.max_framerate.has_value());

	assert(ShouldCouple(0, false, true));
	assert(ShouldCouple(-1, false, true));
	assert(ShouldCouple(60, true, true));
	assert(ShouldCouple(60, false, false));
	assert(!ShouldCouple(60, false, true));
	assert(PositiveRateHint(0) > 0);
	assert(PositiveRateHint(-1, 30) == 30);
	assert(PositiveRateHint(std::numeric_limits<double>::quiet_NaN(), 30) == 30);
	assert(PositiveRateHint(std::numeric_limits<double>::infinity(), 30) == 30);
	assert(PositiveRateHint(144.0) == 144);
	assert(PositiveRateHint(2000.0) == 2000); // Not a fabricated 60/120/999 ceiling.

	FMeasuredRateHint Hint;
	Hint.Reset(0);
	assert(Hint.Get() > 0);
	for (int64_t i = 0; i <= 120; ++i)
	{
		Hint.AddFrame(i * 1000000 / 120);
	}
	assert(Hint.Get() == 120);
	Hint.AddFrame(1000000); // Duplicate/out-of-order timestamps cannot divide by zero.
	Hint.AddFrame(1);
	assert(Hint.Get() == 120);
	for (int64_t i = 1; i <= 30; ++i)
	{
		Hint.AddFrame(1000000 + i * 1000000 / 30);
	}
	assert(Hint.Get() == 30);
	Hint.Reset(48);
	assert(Hint.Get() == 48);
	std::cout << "PASS: uncapped RTP option, capture mode, positive sampled encoder hints\n";
}
