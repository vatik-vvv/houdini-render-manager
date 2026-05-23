"""Houdini-style path helpers for queue and render."""
import os
import re


def norm_path_key(path):
    if not path:
        return ""
    path = path.strip()
    if os.path.isabs(path):
        return os.path.normcase(os.path.abspath(path))
    return os.path.normcase(path.replace("/", os.sep))


def has_frame_tokens(path):
    if not path:
        return False
    return bool(re.search(r"\$F\d*|\$F\b|#+|%0\d+d", path))


def has_houdini_vars(path):
    if not path:
        return False
    return "$" in path


def resolve_houdini_vars(path, hip_file=None, op_name=None):
    """
    Expand Houdini path variables for filesystem checks.
    $HIP  -> directory of the .hip file
    $HIPNAME -> hip filename without extension
    $OS   -> ROP / operator name (e.g. 'front'), NOT a filesystem path
    $F / $F4 / # / % tokens are left for expand_frame_in_path
    """
    if not path:
        return path
    result = path.replace("\\", "/")
    hip_dir = ""
    hip_name = ""
    if hip_file:
        hip_abs = os.path.abspath(hip_file)
        hip_dir = os.path.dirname(hip_abs).replace("\\", "/")
        hip_name = os.path.splitext(os.path.basename(hip_abs))[0]
    if hip_dir:
        result = result.replace("$HIPNAME", hip_name)
        result = result.replace("$HIP", hip_dir)
    if op_name:
        result = result.replace("$OS", op_name)
    return result


def expand_frame_in_path(path, frame, hip_file=None, op_name=None):
    if not path:
        return path
    path = resolve_houdini_vars(path, hip_file, op_name)
    path = re.sub(r"\$F(\d+)", lambda m: str(frame).zfill(int(m.group(1))), path)
    path = re.sub(r"\$F\b", str(frame), path)
    path = re.sub(r"%0(\d+)d", lambda m: f"{frame:0{int(m.group(1))}d}", path)
    if "#" in path:
        hashes = re.search(r"(#+)", path)
        if hashes:
            path = path.replace(hashes.group(1), str(frame).zfill(len(hashes.group(1))))
    return os.path.normpath(path)


def normalize_output_template(output_path):
    """Convert literal frame digits to $F4 only for plain paths (no Houdini vars)."""
    if not output_path:
        return output_path
    if has_frame_tokens(output_path) or "$" in output_path:
        return output_path
    match = re.search(r"(.*?)(\d+)(\.[^./\\]+)$", output_path.replace("\\", "/"))
    if match:
        prefix, digits, ext = match.groups()
        placeholder = f"$F{len(digits)}" if len(digits) > 1 else "$F"
        return f"{prefix}{placeholder}{ext}"
    return output_path


def path_for_hrender(output_path):
    """Path passed to hrender -o: keep Houdini tokens, normalize slashes only."""
    if not output_path:
        return output_path
    return output_path.replace("\\", "/")


def ensure_output_directory(output_path, hip_file, log_callback=None, op_name=None):
    """Create parent folder for render output; resolves $HIP and $OS."""
    if not output_path:
        return
    template = normalize_output_template(output_path)
    fs_path = resolve_houdini_vars(template, hip_file, op_name)
    dir_probe = fs_path
    if has_frame_tokens(dir_probe):
        dir_probe = re.sub(r"\$F\d*", "0001", dir_probe)
        dir_probe = re.sub(r"\$F\b", "1", dir_probe)
        dir_probe = re.sub(r"%0(\d+)d", lambda m: str(1).zfill(int(m.group(1))), dir_probe)
        if "#" in dir_probe:
            hashes = re.search(r"(#+)", dir_probe)
            if hashes:
                dir_probe = dir_probe.replace(hashes.group(1), "1".zfill(len(hashes.group(1))))
    dir_path = os.path.dirname(os.path.normpath(dir_probe))
    if not dir_path:
        return
    if os.path.exists(dir_path):
        return
    try:
        os.makedirs(dir_path, exist_ok=True)
        if log_callback:
            log_callback(f"📁 Created directory: {dir_path}")
    except OSError as e:
        if log_callback:
            log_callback(f"⚠️ Failed to create directory: {dir_path} ({e})")


def path_tooltip(raw_path, hip_file=None, op_name=None):
    if not raw_path:
        return ""
    if hip_file and has_houdini_vars(raw_path):
        resolved = resolve_houdini_vars(raw_path, hip_file, op_name)
        example = expand_frame_in_path(raw_path, 1, hip_file, op_name)
        lines = [raw_path]
        if resolved != raw_path:
            lines.append(f"→ {resolved}")
        if example and example != resolved:
            lines.append(f"frame 1: {example}")
        return "\n".join(lines)
    return raw_path
