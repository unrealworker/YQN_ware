"""Same-pose native views of the second full conveyor audit; no asset writes."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_conveyors as c

c.OUT=c.ROOT/'Saved/MPR/full_workflow_20261107/conveyor_views'/('after' if c.AFTER else 'before')
c.OUT.mkdir(parents=True,exist_ok=True)
c.VIEWS=[
    dict(name='supply_and_placeholders',pivot=[-10380,3290,70],distance=2200,pitch=-55,yaw=-110),
    dict(name='supply_2CCF66',pivot=[-10113.565,2805.388,70],distance=650,pitch=-38,yaw=-65),
    dict(name='supply_2E7F10',pivot=[-10426.005,3684.552,70],distance=700,pitch=-40,yaw=-65),
    dict(name='supply_2CCF62',pivot=[-10737.526,-200.169,70],distance=750,pitch=-40,yaw=-65),
]
c.report.update(views=c.VIEWS,supplemental_views=[],captures=[],scope='Four matching native views; original source locations preserved')

def run():
    yield from c.wait('discover',c.discover)
    for command in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0'):
        c.console(command)
    settings=c.post.get_editor_property('settings')
    c.report['exposure']={key:str(settings.get_editor_property(key)) for key in ('auto_exposure_method','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','bloom_intensity')}
    yield from c.pause(6)
    assert c.roof.open_roof()
    yield from c.wait('open_roof',c.roof.is_interior_available)
    # Keep the old/new simulation from changing the static comparison captures.
    sims=c.u.GameplayStatics.get_all_actors_of_class(c.world,c.u.MPRSorterSimulationActor)
    for sim in sims:sim.set_simulation_playing(False);sim.set_panel_visible(False)
    for view in c.VIEWS:
        c.set_view(view);yield from c.pause(3);yield from c.capture(view)
    if c.AFTER:
        before=json.loads((c.OUT.parent/'before/report.json').read_text(encoding='utf8'))
        assert before['success'] and before['views']==c.VIEWS
        assert before['exposure']==c.report['exposure']
        assert len(before['captures'])==len(c.report['captures'])==4
        for a,b in zip(before['captures'],c.report['captures']):
            assert a['name']==b['name'] and max(abs(x-y) for x,y in zip(a['camera'],b['camera']))<1.e-4
        c.report.update(matching_before_cameras=True,matched_before_view_count=4)
    c.report.update(success=True,stage='complete')

c.steps=run()
