"""Optional workspace-local Node runtime; no global installation or configuration."""
from pathlib import Path
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / '.tools'
target.mkdir(exist_ok=True)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
archive = target/'node.zip'
if not archive.exists():
 print('Downloading Node portable', flush=True)
 with opener.open('https://nodejs.org/dist/v24.22.2/node-v24.22.2-win-x64.zip',timeout=30) as response:
  archive.write_bytes(response.read())
with zipfile.ZipFile(archive) as bundle:
 bundle.extractall(target)
print('Node extracted',flush=True)
