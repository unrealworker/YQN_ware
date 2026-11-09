"""Compile reviewed CAD coordinates into cooked runtime data (no external JSON dependency)."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/sorter_simulation/central_distribution/cad_layout.json'
data=json.loads(SOURCE.read_text(encoding='utf-8-sig'))
def vec(values):return '{'+','.join(f'{x:.8f}' for x in values)+'}'
rows=[]
for w in data['central64']['workers']:
    x,y=w['feed_table']['surface_center_cad_m']
    rows.append('    {'+vec(w['position_ue_cm'])+f",{w['facing_ue_yaw_deg']:.1f},"+vec([x*100,-y*100,103.5])+'},')
text='''// Generated from the original MPR CAD audit. Do not hand-edit surveyed XY.
// Z, carrier count, speed, lift cycle and belt detail are display parameters.
#pragma once
namespace MPRCentralCad
{
struct Worker { double Feet[3]; double Yaw; double Table[3]; };
inline constexpr Worker Workers[] = {
'''+ '\n'.join(rows)+'''\n};
inline constexpr double Center64[3]={-10433.998536,1300.301415,0};
inline constexpr double Center120[3]={-11155.743336,-1636.737051,0};
inline constexpr double Half64=1800,Radius64=54,Half120=367.1,Radius120=44;
inline constexpr const char* SourceSha256="'''+data['source_sha256']+'''";
inline constexpr const char* AuditSha256="'''+hashlib.sha256(SOURCE.read_bytes()).hexdigest()+'''";
}
'''
(ROOT/'Source/Test/MPRCentralCadData.h').write_text(text,encoding='utf-8')
print('Generated central runtime data: six CAD workers, two distribution banks')
