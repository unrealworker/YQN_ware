// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;
using System.Collections.Generic;

public class TestEditorTarget : TargetRules
{
	public TestEditorTarget( TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			WindowsPlatform.CompilerVersion = "14.38.33130";
		}
		ExtraModuleNames.Add("Test");
	}
}
