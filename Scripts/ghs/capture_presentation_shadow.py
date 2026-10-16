from pathlib import Path
root=Path(r'D:\UEPro\Test')
source=(root/'Scripts/ghs/capture_presentation.py').read_text()
source=source.replace("'GHS_Presentation'+phase", "'GHS_PresentationShadow'")
exec(compile(source,str(root/'Scripts/ghs/capture_presentation.py'),'exec'),globals())
