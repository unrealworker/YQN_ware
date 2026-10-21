// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;
using System.Collections.Generic;

public class TestGameTarget : TargetRules
{
	public TestGameTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			WindowsPlatform.CompilerVersion = "14.38.33130";
		}
		ExtraModuleNames.Add("Test");
	}
}
