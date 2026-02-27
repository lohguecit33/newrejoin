import zlib
import base64
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)

INPUT_FILE  = "ova.py"
OUTPUT_FILE = "ova_obf.py"

with open(INPUT_FILE, "rb") as f:
    raw = f.read()

payload = base64.b64encode(zlib.compress(raw))[::-1]

loader = f'''import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

_ = lambda __ : __import__('zlib').decompress(
    __import__('base64').b64decode(__[::-1])
)

exec((_)(b'{payload.decode()}'))
'''

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(loader)

print("✔ Obfuscation selesai → ova_obf.py")
