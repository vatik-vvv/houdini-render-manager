try:
    import hou
except ImportError:
    hou = None

def get_houdini_version():
    if hou:
        version = hou.applicationVersion()
        return f"{version[0]}.{version[1]}.{version[2]}"
    else:
        return "Houdini not available"
