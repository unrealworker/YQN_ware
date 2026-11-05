"""Visual recipe shared by both review rounds; CAD metres and sRGB swatches."""
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
DEST = '/Game/MPRWarehouse/SiteComplete'
FOV = 50.0
VIEWS = [
    ['01-overview', [65, -5, 0], 110000, -52, -90, False],
    ['02-docks-parking', [-55, -110, 0], 44000, -55, -88, False],
    ['03-north-west', [-80, 65, 0], 49000, -58, -115, False],
]
COLORS = {
    'MPR4_RoofMembrane': 'E8EDF0', 'MPR4_FacadeWhite': 'DCE2E5',
    'MPR4_IndustrialBlue': '205581',
    'MPR3_Grass': 'B7C1AC', 'MPRR_CampusGreen': 'ACBA9E',
    'MPR3_Concrete': 'C9CCCB', 'MPR4_TerminalCurb': 'D0D3D1',
    'MPR3_Asphalt': '7A8490', 'MPR4_TerminalAsphalt': '7A8490',
    'MPRR_ContextPaving': 'B9BDBD',
    'MPRR_ContextRoof': 'DFE4E7', 'MPRR_ContextWall': 'D6DDE0',
    'MPRR_ContextTrim': 'DCE1E2',
    'MPRR_LeafMid': 'A3B397', 'MPRR_LeafLight': 'B7C4AD',
    'MPRR_LeafShade': '8C9F81',
}

def linear(hex_color):
    v = [int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4)]
    return [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in v]
