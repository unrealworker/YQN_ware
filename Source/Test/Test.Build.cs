// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class Test : ModuleRules
{
	public Test(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "UniversalCameraPlugin", "UMG" });

		PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		RuntimeDependencies.Add("$(ProjectDir)/Content/GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf", StagedFileType.NonUFS);
		RuntimeDependencies.Add("$(ProjectDir)/Content/GHSNormalWarehouse/HUD/Fonts/LICENSE.txt", StagedFileType.NonUFS);

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		
		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
