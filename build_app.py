import os
import shutil
import subprocess
import sys
from pathlib import Path


def build():
    print("=== Building DCU Room Finder.app ===")

    # Generate icons first
    subprocess.run([sys.executable, "generate_assets.py"], check=True)

    # Run PyInstaller
    spec_path = "DCU Room Finder.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_path,
    ]
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)

    if res.returncode != 0:
        print("Build failed!")
        sys.exit(res.returncode)

    app_bundle = Path("dist/DCU Room Finder.app")
    if app_bundle.exists():
        print(f"SUCCESS: Successfully generated macOS application bundle at {app_bundle.resolve()}")
        print("You can drag 'dist/DCU Room Finder.app' into /Applications or directly onto your macOS Dock.")
    else:
        print("ERROR: Application bundle not found in dist/")
        sys.exit(1)


if __name__ == "__main__":
    build()
