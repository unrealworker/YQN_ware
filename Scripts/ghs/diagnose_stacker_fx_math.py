"""Disposable commandlet-only transform diagnostic; never load/save a map."""
import unreal,json,math
from pathlib import Path
assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
out=[]
def xyz(v):return [v.x,v.y,v.z]
for yaw in (0,180,360):
 t=unreal.Transform(rotation=unreal.Rotator(pitch=-90,yaw=yaw,roll=0))
 r=t.rotation.rotator();v=unreal.MathLibrary.transform_direction(t,unreal.Vector(0,1,0))
 out.append(dict(input_yaw=yaw,output=[r.pitch,r.yaw,r.roll],right=xyz(v),expected=[-math.sin(math.radians(yaw)),math.cos(math.radians(yaw)),0]))
report=dict(rotations=out,relative_transform_exposed=hasattr(unreal.SceneComponent,'get_relative_transform'))
Path(r'D:\UEPro\Test\Saved\GHS_NormalStackerFXMathDiagnostic.json').write_text(json.dumps(report,indent=2))
unreal.log('STACKER_FX_MATH_DIAGNOSTIC '+json.dumps(report))
