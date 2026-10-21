"""Select a real device in the live preview before the OS middle-click check."""
import unreal
found=False
for world in unreal.ObjectIterator(unreal.World):
    pc=unreal.GameplayStatics.get_player_controller(world,0)
    if not pc or not hasattr(pc,'twin_hud_widget'): continue
    widget=pc.get_editor_property('twin_hud_widget')
    if widget:
        assert widget.select_object('AGV-34',True)
        found=True; break
assert found,'Start the current scene preview first'
