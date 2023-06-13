import json
import platform
import requests
import stat
import subprocess
from pathlib import Path
from robocorp.tasks import task

ROBO_RELEASES_URL = "https://downloads.robocorp.com/robo/releases/index.json"
ROBO_TEMPLATES = [
    "browser",
    "workitems",
]

@task
def generate_template():
    if platform.system() == "Windows":
        raise NotImplementedError("Requires Linux/macOS")

    ensure_robo()

    for template in ROBO_TEMPLATES:
        print("Creating from template:", template)
        subprocess.run(["robo", "new", "-t", template], check=True)


def ensure_robo():
    path = Path("robo")
    if path.exists():
        return

    response = requests.get(ROBO_RELEASES_URL, allow_redirects=True)
    releases = json.loads(response.content)
    latest = releases["edge"][0]

    if platform.system() == "Linux":
        exe_url = latest["linux"]
    else:
        exe_url = latest["macos"]

    print("Downloading robo:", exe_url)
    response = requests.get(exe_url, allow_redirects=True)
    with open(path, "wb") as fd:
        fd.write(response.content)

    path.chmod(path.stat().st_mode | stat.S_IEXEC)
