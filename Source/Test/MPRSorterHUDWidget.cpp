#include "MPRSorterHUDWidget.h"
#include "MPRSorterSimulationActor.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Fonts/SlateFontInfo.h"
#include "Misc/Paths.h"
#include "Styling/SlateTypes.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
FLinearColor MPRColor(const TCHAR* Hex) {return FLinearColor::FromSRGBColor(FColor::FromHex(Hex));}
FSlateFontInfo MPRFont(int32 Size)
{
    return FSlateFontInfo(FPaths::ProjectContentDir()/TEXT("GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf"),Size);
}
const FSlateBrush* MPRPanelBrush()
{
    static const FSlateRoundedBoxBrush Brush(FLinearColor::White,10.f,MPRColor(TEXT("D6DFEC")),1.f);
    return &Brush;
}
const FButtonStyle* MPRButtonStyle()
{
    // Static brushes/style outlive every Slate widget that references them.
    static const FButtonStyle Style=FButtonStyle()
        .SetNormal(FSlateRoundedBoxBrush(FLinearColor::White,6.f,MPRColor(TEXT("CFDAE8")),1.f))
        .SetHovered(FSlateRoundedBoxBrush(MPRColor(TEXT("EDF3FF")),6.f,MPRColor(TEXT("356BFA")),1.f))
        .SetPressed(FSlateRoundedBoxBrush(MPRColor(TEXT("DCE8FF")),6.f,MPRColor(TEXT("356BFA")),1.f))
        .SetDisabled(FSlateRoundedBoxBrush(MPRColor(TEXT("F1F3F6")),6.f,MPRColor(TEXT("DCE2EA")),1.f))
        .SetNormalPadding(FMargin(7,3)).SetPressedPadding(FMargin(7,3));
    return &Style;
}

/** Consume only events hit-tested within the visible panel. Its surrounding
 * SBox does not handle input, so the existing GHS camera retains the scene.
 */
class SMPRSorterPanel final : public SBorder
{
public:
    SLATE_BEGIN_ARGS(SMPRSorterPanel) {}
        SLATE_DEFAULT_SLOT(FArguments,Content)
    SLATE_END_ARGS()
    void Construct(const FArguments& Args)
    {SBorder::Construct(SBorder::FArguments().BorderImage(MPRPanelBrush()).Padding(FMargin(12,10))[Args._Content.Widget]);}
    virtual FReply OnMouseButtonDown(const FGeometry&,const FPointerEvent&) override {return FReply::Handled();}
    virtual FReply OnMouseButtonUp(const FGeometry&,const FPointerEvent&) override {return FReply::Handled();}
    virtual FReply OnMouseButtonDoubleClick(const FGeometry&,const FPointerEvent&) override {return FReply::Handled();}
    virtual FReply OnMouseWheel(const FGeometry&,const FPointerEvent&) override {return FReply::Handled();}
    virtual FReply OnMouseMove(const FGeometry&,const FPointerEvent&) override {return FReply::Handled();}
    virtual bool SupportsKeyboardFocus() const override {return false;}
};
}

void UMPRSorterHUDWidget::InitializeSorter(AMPRSorterSimulationActor* Actor)
{
    Owner=Actor;
    SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    SetIsFocusable(false);
}

TSharedRef<SWidget> UMPRSorterHUDWidget::RebuildWidget()
{
    const FSlateColor Ink(MPRColor(TEXT("25364B"))),Muted(MPRColor(TEXT("536478"))),Blue(MPRColor(TEXT("356BFA")));
    auto Ready=[this](){return Owner.IsValid()&&Owner->IsReady();};
    using FAction=TFunction<void(AMPRSorterSimulationActor&)>;
    auto Button=[this,Ready,Ink,Blue](TFunction<FText()> Caption,FAction Action,double Rate=0.)->TSharedRef<SWidget>
    {
        return SNew(SButton)
            .ButtonStyle(MPRButtonStyle()).IsFocusable(false).IsEnabled_Lambda(Ready)
            .HAlign(HAlign_Center).VAlign(VAlign_Center)
            .OnClicked_Lambda([this,Action](){if(auto* A=Owner.Get();A&&A->IsReady())Action(*A);return FReply::Handled();})
            [SNew(STextBlock).Font(MPRFont(12)).Text_Lambda([Caption](){return Caption();})
             .ColorAndOpacity_Lambda([this,Rate,Ink,Blue](){return Rate>0.&&Owner.IsValid()&&Owner->GetSimulationRate()==Rate?Blue:Ink;})];
    };
    auto StaticCaption=[](const TCHAR* Text)->TFunction<FText()>{const FText Value=FText::FromString(Text);return [Value](){return Value;};};
    auto Read=[this](FString(AMPRSorterSimulationActor::*Getter)()const,const TCHAR* Fallback)->TAttribute<FText>
    {
        const FString Empty=Fallback;
        return TAttribute<FText>::CreateLambda([this,Getter,Empty](){auto* A=Owner.Get();return FText::FromString(A?(A->*Getter)():Empty);});
    };
    auto Content=SNew(SVerticalBox)
        +SVerticalBox::Slot().AutoHeight()
        [SNew(SHorizontalBox)
            +SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
            [SNew(STextBlock).Text(FText::FromString(TEXT("天工木马 · 作业仿真"))).Font(MPRFont(15)).ColorAndOpacity(Ink)]
            +SHorizontalBox::Slot().AutoWidth()
            [SNew(SButton).ButtonStyle(MPRButtonStyle()).IsFocusable(false)
                .OnClicked_Lambda([this](){bCollapsed=!bCollapsed;return FReply::Handled();})
                [SNew(STextBlock).Font(MPRFont(11)).ColorAndOpacity(Muted)
                    .Text_Lambda([this](){return FText::FromString(bCollapsed?TEXT("展开"):TEXT("收起"));})]]]
        +SVerticalBox::Slot().AutoHeight().Padding(0,8,0,0)
        [SNew(SVerticalBox).Visibility_Lambda([this](){return bCollapsed?EVisibility::Collapsed:EVisibility::Visible;})
            +SVerticalBox::Slot().AutoHeight()
            [SNew(SBox).HeightOverride(22)[SNew(STextBlock).Font(MPRFont(13)).ColorAndOpacity(Ink)
                .Text(Read(&AMPRSorterSimulationActor::GetMachineTitle,TEXT("正在准备设备…")))]]
            +SVerticalBox::Slot().AutoHeight()
            [SNew(SBox).HeightOverride(20)[SNew(STextBlock).Font(MPRFont(12)).ColorAndOpacity(Blue)
                .Text(Read(&AMPRSorterSimulationActor::GetStatusText,TEXT("等待初始化")))]]
            +SVerticalBox::Slot().AutoHeight()
            [SNew(SBox).HeightOverride(66)[SNew(STextBlock).Font(MPRFont(12)).ColorAndOpacity(Ink).AutoWrapText(true)
                .Text(Read(&AMPRSorterSimulationActor::GetProgressText,TEXT("")))
                .ToolTipText(Read(&AMPRSorterSimulationActor::GetProgressText,TEXT("")))]]
            +SVerticalBox::Slot().AutoHeight()
            [SNew(SBox).HeightOverride(32)[SNew(STextBlock).Font(MPRFont(11)).ColorAndOpacity(Muted).AutoWrapText(true)
                .Text(Read(&AMPRSorterSimulationActor::GetCarrierText,TEXT("")))
                .ToolTipText(Read(&AMPRSorterSimulationActor::GetCarrierText,TEXT("")))]]
            +SVerticalBox::Slot().AutoHeight().Padding(0,6,0,0)
            [SNew(SBox).HeightOverride(28)[SNew(SHorizontalBox)
                +SHorizontalBox::Slot().FillWidth(1.45f).Padding(0,0,4,0)
                [Button([this](){return FText::FromString(Owner.IsValid()&&Owner->IsSimulationPlaying()?TEXT("暂停"):TEXT("开始"));},
                    [](AMPRSorterSimulationActor& A){A.SetSimulationPlaying(!A.IsSimulationPlaying());})]
                +SHorizontalBox::Slot().FillWidth(1.1f).Padding(0,0,4,0)
                [Button(StaticCaption(TEXT("复位")),[](AMPRSorterSimulationActor& A){A.ResetSimulation();})]
                +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,4,0)
                [Button(StaticCaption(TEXT("1×")),[](AMPRSorterSimulationActor& A){A.SetSimulationRate(1);},1)]
                +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,4,0)
                [Button(StaticCaption(TEXT("2×")),[](AMPRSorterSimulationActor& A){A.SetSimulationRate(2);},2)]
                +SHorizontalBox::Slot().FillWidth(1)
                [Button(StaticCaption(TEXT("4×")),[](AMPRSorterSimulationActor& A){A.SetSimulationRate(4);},4)]]]
            +SVerticalBox::Slot().AutoHeight().Padding(0,5,0,0)
            [SNew(SBox).HeightOverride(28)[SNew(SHorizontalBox)
                +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,5,0)
                [Button(StaticCaption(TEXT("上一台")),[](AMPRSorterSimulationActor& A){const int32 N=A.GetMachineCount();if(N>0)A.FocusMachine((A.GetSelectedMachineIndex()+N-1)%N);})]
                +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,5,0)
                [Button(StaticCaption(TEXT("定位设备")),[](AMPRSorterSimulationActor& A){if(A.GetMachineCount()>0)A.FocusMachine(A.GetSelectedMachineIndex());})]
                +SHorizontalBox::Slot().FillWidth(1)
                [Button(StaticCaption(TEXT("下一台")),[](AMPRSorterSimulationActor& A){const int32 N=A.GetMachineCount();if(N>0)A.FocusMachine((A.GetSelectedMachineIndex()+1)%N);})]]]
            +SVerticalBox::Slot().AutoHeight().Padding(0,5,0,0)
            [SNew(SBox).HeightOverride(28)[SNew(SHorizontalBox)
                +SHorizontalBox::Slot().FillWidth(1.4f).VAlign(VAlign_Center).Padding(0,0,5,0)
                [SNew(SCheckBox).IsFocusable(false).IsEnabled_Lambda(Ready)
                    .IsChecked_Lambda([this](){return Owner.IsValid()&&Owner->IsAutomaticCollection()?ECheckBoxState::Checked:ECheckBoxState::Unchecked;})
                    .OnCheckStateChanged_Lambda([this](ECheckBoxState State){if(auto* A=Owner.Get();A&&A->IsReady())A->SetAutomaticCollection(State==ECheckBoxState::Checked);})
                    [SNew(STextBlock).Font(MPRFont(12)).ColorAndOpacity(Ink).Text(FText::FromString(TEXT("自动换整车")))]]
                +SHorizontalBox::Slot().FillWidth(1)
                [Button(StaticCaption(TEXT("更换满车")),[](AMPRSorterSimulationActor& A){A.ClearFullBins();})]]]];

    // The caller may reserve a taller viewport slot. Only this top-aligned,
    // content-sized border draws and hit-tests; the unused area stays transparent.
    return SNew(SBox).WidthOverride(360).VAlign(VAlign_Top)
        [SNew(SMPRSorterPanel)[Content]];
}
