"""Cross-platform SF Pro font resolution (Windows / macOS / Linux)."""
import glob
import os
import platform


def find_font(filename):
    """Locate a system font file by name on whatever OS this is running on."""
    system = platform.system()
    if system == "Darwin":
        search_dirs = ["/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    elif system == "Windows":
        search_dirs = [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
            os.path.expandvars(r"%WINDIR%\Fonts"),
        ]
    else:
        search_dirs = ["/usr/share/fonts", os.path.expanduser("~/.fonts")]

    for d in search_dirs:
        path = os.path.join(d, filename)
        if os.path.exists(path):
            return path
        matches = glob.glob(os.path.join(d, "**", filename), recursive=True)
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"Could not find font '{filename}' on this system ({system}).\n"
        "Install SF Pro Display/Text from Apple's developer site:\n"
        "  macOS: open the .otf files and click Install (lands in ~/Library/Fonts)\n"
        "  Windows: right-click the .otf files and Install (lands in "
        "%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts)"
    )
