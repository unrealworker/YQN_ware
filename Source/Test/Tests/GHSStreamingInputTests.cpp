#if WITH_DEV_AUTOMATION_TESTS
#include "../GHSStreamingInputComponent.h"
#include "GHSAutomationTestFlags.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGHSPS2ChineseInputTest,"GHS.Streaming.PixelStreaming2.ChineseUIInteraction",GHSAutomationTests::ApplicationContextMask|EAutomationTestFlags::ProductFilter)
bool FGHSPS2ChineseInputTest::RunTest(const FString&)
{
    const FString Expected=TEXT("{\"type\":\"search\",\"query\":\"人工叉车 02 / 地堆\"}");
    const auto UTF16=StringCast<UTF16CHAR>(*Expected);
    TArray<uint8> Packet;
    FMemoryWriter Writer(Packet);
    uint16 Length=uint16(UTF16.Length()); Writer<<Length;
    Writer.Serialize(const_cast<UTF16CHAR*>(UTF16.Get()),Length*sizeof(UTF16CHAR));
    FString Result;
    FMemoryReader Reader(Packet);
    TestTrue(TEXT("Decode the frontend's length-prefixed UTF16 payload"),UGHSStreamingInputComponent::ReadDescriptor(Reader,Result));
    TestEqual(TEXT("Preserve Chinese search without mojibake"),Result,Expected);
    Packet.Pop();
    FMemoryReader Truncated(Packet); Result=TEXT("unchanged");
    TestFalse(TEXT("Reject a truncated UTF16 code unit"),UGHSStreamingInputComponent::ReadDescriptor(Truncated,Result));
    TestEqual(TEXT("Invalid input does not overwrite output"),Result,FString(TEXT("unchanged")));
    TArray<uint8> Empty;
    FMemoryReader EmptyReader(Empty);
    TestFalse(TEXT("Reject missing length prefix"),UGHSStreamingInputComponent::ReadDescriptor(EmptyReader,Result));
    return true;
}
#endif
