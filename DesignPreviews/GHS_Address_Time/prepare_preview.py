from pathlib import Path
from PIL import Image
from io import BytesIO
import base64

folder = Path(__file__).parent
source = Path('D:/UEPro/Test/Design/GHS_Twin_SaaS_Concept/assets/warehouse-poi/roof-campus.png')
with Image.open(source) as image:
    image = image.convert('RGB')
    image.thumbnail((1920, 1200))
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=83, optimize=True)
data = 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
fragment = folder / 'ghs-address-clock.html'
text = fragment.read_text(encoding='utf-8')
assert '__SCENE_DATA__' in text
fragment.write_text(text.replace('__SCENE_DATA__', data), encoding='utf-8')
assert fragment.stat().st_size < 1024 * 1024
print({'preview_bytes':fragment.stat().st_size, 'scene_bytes':len(buffer.getvalue())})
