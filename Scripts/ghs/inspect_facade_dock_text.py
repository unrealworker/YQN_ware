"""Capture a dock-text baseline once; never replace a complete baseline."""
import json
from pathlib import Path
import unreal
out=Path('D:/UEPro/Test/Saved/FacadeExpansion/Before/dock_text.json')
previous=json.loads(out.read_text(encoding='utf-8')) if out.exists() else None
numbers=set(range(75,79))|set(range(51,54))|set(range(30,34))
rows=[]
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    label=actor.get_actor_label()
    if not label.startswith('GHS_DockNumber_') or int(label.split('_')[-1]) not in numbers:continue
    c=actor.get_component_by_class(unreal.TextRenderComponent)
    color=c.text_render_color
    origin,extent,radius=unreal.SystemLibrary.get_component_bounds(c)
    rows.append(dict(label=label,text=str(c.text),world_size=c.world_size,
        material=c.text_material.get_path_name(),font=c.font.get_path_name() if c.font else None,
        color=[color.r,color.g,color.b,color.a],
        horizontal_alignment=str(c.horizontal_alignment),vertical_alignment=str(c.vertical_alignment),
        text_bounds=dict(min=[origin.x-extent.x,origin.y-extent.y,origin.z-extent.z],
                         max=[origin.x+extent.x,origin.y+extent.y,origin.z+extent.z])))
assert len(rows)==11
rows.sort(key=lambda row:row['label'])
if previous is not None:
    # Font was absent from the old baseline. Compare every property that was
    # actually recorded; never fill old evidence using a later font value.
    previous=sorted(previous,key=lambda row:row['label'])
    assert len(previous)==11
    current={row['label']:row for row in rows}
    assert set(current)=={row['label'] for row in previous}
    for old in previous:
        actual=current[old['label']]
        for key,value in old.items():
            if key!='text_bounds':
                assert actual[key]==value,(old['label'],key,'Dock text changed since baseline')
    missing=[row for row in previous if 'text_bounds' not in row]
    if missing:
        # A legacy bounds upgrade is valid only before the original actor has
        # moved; adding current post-cladding bounds would corrupt the baseline.
        scene=json.loads((out.parent/'scene_state.json').read_text(encoding='utf-8'))
        positions={row['label']:row['transform']['position'] for row in scene['actors']}
        actors={actor.get_actor_label():actor for actor in
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()}
        for old in missing:
            position=actors[old['label']].get_actor_location()
            assert all(abs(a-b)<.01 for a,b in zip((position.x,position.y,position.z),positions[old['label']])), \
                (old['label'],'Cannot retrofit pre-change bounds after moving the actor')
            old['text_bounds']=current[old['label']]['text_bounds']
        out.write_text(json.dumps(previous,indent=2),encoding='utf-8')
    else:
        unreal.log('GHS_DOCK_TEXT_BASELINE_PRESERVED_READ_ONLY')
else:
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
