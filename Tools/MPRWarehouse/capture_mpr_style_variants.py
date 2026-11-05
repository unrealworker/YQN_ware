"""Read-only runtime lighting/material samples, before authoring final sources."""
from pathlib import Path
import sys
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
import capture_mpr_reference_runtime_views as capture
base=capture.base
capture.OUT=base.ROOT/'Saved/MPR/style_review/variants';capture.OUT.mkdir(parents=True,exist_ok=True)
capture.VIEWS=[(name,[0,0,14],76000,-52,-90,False)for name in ['00-current','01-materials','02-key-contrast','03-balanced']]
original=capture.set_view
dynamic=[];lights={}
COLORS={
 'MPR4_RoofMembrane':[1.,1.,1.],
 'MPR3_Concrete':[.42,.445,.46],
 'MPR3_Grass':[.31,.35,.31],'MPR3_GrassFar':[.31,.35,.31],
 'MPR4_LeafMid':[.26,.33,.255],'MPR4_LeafLight':[.35,.40,.32],'MPR4_LeafShade':[.19,.26,.19],
 'MPR4_ContextRoof':[.47,.49,.54],
}

def set_view():
    if not lights:
        for a in u.GameplayStatics.get_all_actors_of_class(base.world,u.Actor):
            label=a.get_actor_label()
            if label=='MPR4_KeyLight':lights['sun']=a.get_component_by_class(u.DirectionalLightComponent)
            elif label=='MPR4_Ambient':lights['sky']=a.get_component_by_class(u.SkyLightComponent)
            elif label=='MPR4_ReferenceStyle':lights['post']=a
            for c in a.get_components_by_class(u.StaticMeshComponent):
                for i,m in enumerate(c.get_materials()):
                    if not m:continue
                    role=m.get_name().removeprefix('MI_')
                    if role not in COLORS:continue
                    dm=c.create_dynamic_material_instance(i,m);dynamic.append((role,dm))
    if capture.index:
        for role,dm in dynamic:dm.set_vector_parameter_value('Tint',u.LinearColor(*COLORS[role],1))
    sun,sky,bias=[(3.8,.65,.45),(3.8,.65,.45),(4.6,.45,.45),(4.3,.55,.60)][capture.index]
    lights['sun'].set_intensity(sun);lights['sky'].set_intensity(sky)
    s=lights['post'].get_editor_property('settings');s.set_editor_property('auto_exposure_bias',bias);lights['post'].set_editor_property('settings',s)
    capture.report.setdefault('variants',[]).append(dict(name=capture.VIEWS[capture.index][0],sun=sun,sky=sky,exposure_bias=bias,colors=COLORS if capture.index else {}))
    original()

capture.set_view=set_view
