using UnrealBuildTool;

public class GHSDisplayBootstrap : ModuleRules
{
    public GHSDisplayBootstrap(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "ApplicationCore" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Engine", "Slate", "SlateCore" });
    }
}
