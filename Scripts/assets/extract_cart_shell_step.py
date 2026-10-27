"""Read the STEP assembly with OpenCascade, preserving placements and colors.

Requires cadquery-ocp 7.7.2 in Saved/StepTools under the project's UE Python 3.11.
Outputs an intermediate triangulation and a compact CAD audit in Saved/CartShell1026.
"""
from pathlib import Path
import json
import sys
import math
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Saved/StepTools'))
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.Quantity import Quantity_Color

SOURCE = Path(r'D:\DDDownload\小车外壳（1026）.STEP')
OUT = ROOT / 'Saved/CartShell1026'
OUT.mkdir(parents=True, exist_ok=True)
# An ASCII path also avoids Windows narrow-character path handling in OpenCascade.
cad_path = OUT / 'source.step'
cad_path.write_bytes(SOURCE.read_bytes())
doc = TDocStd_Document(TCollection_ExtendedString('GHS_CartShell_1026'))
reader = STEPCAFControl_Reader()
reader.SetColorMode(True)
reader.SetNameMode(True)
status = reader.ReadFile(str(cad_path))
assert int(status) == 1, status
assert reader.Transfer(doc)
shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
parts = []

def label_name(label):
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        name = attr.Get().ToExtString()
        try:
            return name.encode('latin1').decode('gb18030')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return name
    return 'unnamed'

def get_color(entity, default=(.7, .73, .79)):
    c = Quantity_Color()
    for mode in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
        getter = color_tool.GetColor_s if isinstance(entity, TDF_Label) else color_tool.GetColor
        if getter(entity, mode, c):
            return tuple(round(v, 5) for v in (c.Red(), c.Green(), c.Blue()))
    return default

def walk(label, placement=TopLoc_Location(), trail=()):
    name = label_name(label)
    if shape_tool.IsReference_s(label):
        referred = TDF_Label()
        shape_tool.GetReferredShape_s(label, referred)
        return walk(referred, placement.Multiplied(shape_tool.GetLocation_s(label)), trail+(name,))
    if shape_tool.IsAssembly_s(label):
        seq = TDF_LabelSequence()
        shape_tool.GetComponents_s(label, seq)
        for i in range(1, seq.Length()+1):
            walk(seq.Value(i), placement, trail+(name,))
        return
    shape = shape_tool.GetShape_s(label)
    if shape.IsNull():
        return
    BRepMesh_IncrementalMesh(shape, .55, False, .70, True).Perform()
    vertices, triangles, colors, face_ids = [], [], [], []
    default = get_color(shape, get_color(label))
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_count = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            transform = placement.Multiplied(loc).Transformation()
            base = len(vertices)
            color = get_color(face, default)
            for i in range(1, tri.NbNodes()+1):
                p = tri.Node(i).Transformed(transform)
                vertices.append([round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6)])
            for i in range(1, tri.NbTriangles()+1):
                a,b,c = tri.Triangle(i).Get()
                if face.Orientation() == TopAbs_REVERSED:
                    b,c = c,b
                triangles.append([base+a-1, base+b-1, base+c-1])
                colors.append(color)
                face_ids.append(face_count)
        face_count += 1
        explorer.Next()
    if not triangles:
        return
    mins = [min(p[k] for p in vertices) for k in range(3)]
    maxs = [max(p[k] for p in vertices) for k in range(3)]
    part = dict(index=len(parts), name=name, assembly_path=trail, vertices_mm=vertices,
                triangles=triangles, colors=colors, face_ids=face_ids, source_faces=face_count,
                bounds_mm=[mins,maxs], size_mm=[round(maxs[k]-mins[k],3) for k in range(3)])
    parts.append(part)
    print('PART',part['index'],repr(name),part['size_mm'],len(triangles),flush=True)

roots = TDF_LabelSequence()
shape_tool.GetFreeShapes(roots)
for i in range(1, roots.Length()+1):
    walk(roots.Value(i))
lo=[min(p['bounds_mm'][0][k] for p in parts) for k in range(3)]
hi=[max(p['bounds_mm'][1][k] for p in parts) for k in range(3)]
result=dict(source=str(SOURCE),units='millimeter',bounds_mm=[lo,hi],
            size_mm=[round(hi[k]-lo[k],3) for k in range(3)],parts=parts)
(OUT/'assembly_mesh.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
audit={k:v for k,v in result.items() if k!='parts'}
audit['parts']=[{k:v for k,v in p.items() if k not in ('vertices_mm','triangles','colors')}|
                dict(triangles=len(p['triangles']),palette=sorted(set(tuple(c) for c in p['colors']))) for p in parts]
audit['triangle_count']=sum(len(p['triangles']) for p in parts)
(OUT/'cad_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
print('COMPLETE',len(parts),'parts',audit['triangle_count'],'triangles',result['size_mm'],flush=True)
