"""Resolve installed tools without embedding a developer's drive or username.

Call these helpers after parsing arguments so --help never requires EDA tools.
Explicit command-line paths take priority, followed by PQC_* variables, PATH,
and the installation variables populated by AMD settings scripts.
"""
from pathlib import Path
import argparse
import os
import shutil


def _executables(name):
    if os.name == "nt" and not Path(name).suffix:
        return (name + ".bat", name + ".exe", name + ".cmd", name)
    return (name,)


def _existing(value):
    if not value:
        return None
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    path = Path(expanded)
    if path.is_file():
        return path.resolve()
    found = shutil.which(expanded)
    return Path(found).resolve() if found else None


def _at(directory, name):
    if directory:
        for exe in _executables(name):
            found = _existing(Path(directory) / exe)
            if found:
                return found
    return None


def tool_path(name, override=None):
    """Return an executable Path; accept an explicit path or command name."""
    env_name = "PQC_" + name.upper()
    configured = override or os.environ.get(env_name)
    if configured:
        found = _existing(configured)
        if not found:
            raise FileNotFoundError(f"{name} executable not found: {configured}")
        return found
    if name == "bash" and os.name == "nt":
        # Windows' System32/bash.exe starts WSL and does not accept Git paths.
        git = _existing("git")
        if git:
            for directory in (git.parent, git.parent.parent / "bin"):
                found = _at(directory, "bash")
                if found:
                    return found
    for exe in _executables(name):
        found = _existing(exe)
        if found:
            return found
    roots = []
    if name in {"vivado", "xvlog", "xelab", "xsim"}:
        roots = [os.environ.get("XILINX_VIVADO")]
        if name != "vivado":
            configured_vivado = _existing(os.environ.get("PQC_VIVADO"))
            if configured_vivado:
                found = _at(configured_vivado.parent, name)
                if found:
                    return found
    elif name == "vitis_hls":
        roots = [os.environ.get("XILINX_HLS"), os.environ.get("XILINX_VITIS_HLS"),
                 os.environ.get("XILINX_VITIS")]
    for root in roots:
        if root:
            found = _at(Path(root) / "bin", name)
            if found:
                return found
    raise FileNotFoundError(
        f"Cannot find {name}. Put it on PATH, source the AMD settings script, "
        f"or set {env_name} to its executable.")


def riscv_tool(name, tool_dir=None):
    """Find a riscv64-unknown-elf tool (RV32 code is selected by build flags)."""
    executable = "riscv64-unknown-elf-" + name
    directory = tool_dir or os.environ.get("PQC_RISCV_TOOL_DIR")
    if directory:
        found = _at(directory, executable)
        if not found:
            raise FileNotFoundError(f"Missing {executable} in {directory}")
        return found
    for candidate in _executables(executable):
        found = _existing(candidate)
        if found:
            return found
    root = os.environ.get("XILINX_VIVADO")
    if not root:
        try:
            root = tool_path("vivado").parent.parent
        except FileNotFoundError:
            pass
    if root:
        platform = "nt" if os.name == "nt" else "lin"
        for suffix in (("gnu", "riscv", platform, "riscv64-unknown-elf", "bin"),
                       ("gnu", "riscv", platform, "bin")):
            found = _at(Path(root).joinpath(*suffix), executable)
            if found:
                return found
    raise FileNotFoundError(
        f"Cannot find {executable}. Set PQC_RISCV_TOOL_DIR or --tool-dir, "
        "or put the RISC-V toolchain on PATH.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", help="Executable name, or riscv")
    parser.add_argument("--path", help="Explicit executable path")
    parser.add_argument("--name", default="gcc", help="RISC-V subtool")
    parser.add_argument("--tool-dir", type=Path)
    args = parser.parse_args()
    try:
        print(riscv_tool(args.name, args.tool_dir) if args.tool == "riscv"
              else tool_path(args.tool, args.path))
    except FileNotFoundError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
