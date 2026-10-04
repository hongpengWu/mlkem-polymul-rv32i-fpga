"""Build ML-KEM-1024 KAT with exclusively hardware FIPS 202; no RTL run."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path("E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def board_vectors(out):
    """Use the same verified public cases as the host-driven KAT runner."""
    sys.path.insert(0, str(ROOT / "scripts/kat"))
    from package_mlkem import ACVP_COMMIT, load_cases, pack_fixture, verify_roundtrip
    all_cases, sources = load_cases(ROOT, 1024)
    indices = [0, 1, 115]
    cases = deepcopy([all_cases[i] for i in indices])
    for index, case in enumerate(cases):
        case["case_index"] = index
    require([case["op"] for case in cases] == [1, 2, 3], "Board subset operation mismatch")
    header = ["/* Generated from pinned public ACVP; never edit manually. */",
              "#ifndef PICO_BOARD_VECTORS_H", "#define PICO_BOARD_VECTORS_H",
              "#include <stdint.h>", "#define BOARD_CASES 3u"]
    paths = []
    for expected, direction in ((False, "input"), (True, "expected")):
        words = pack_fixture(cases, 1024, expected)
        fixture = out / f"board_{direction}.mem"
        fixture.write_text("".join(f"{word:08x}\n" for word in words), encoding="ascii", newline="\n")
        verify_roundtrip(fixture, cases, 1024, expected)
        paths.append(fixture)
        header += [f"#define BOARD_{direction.upper()}_WORDS {len(words)}u",
                   f"static const uint32_t board_{direction}[{len(words)}] = {{"]
        header += ["    " + ", ".join(f"UINT32_C(0x{word:08x})" for word in words[i:i+8]) + ","
                   for i in range(0, len(words), 8)]
        header.append("};")
    header.append("#endif")
    generated = out / "board_vectors.h"
    generated.write_text("\n".join(header)+"\n", encoding="ascii", newline="\n")
    paths.append(generated)
    metadata = dict(original_indices=indices, local_indices=[0, 1, 2], cases=cases,
        acvp_commit=ACVP_COMMIT, sources=sources,
        manifest_sha256=sha(ROOT / "vectors/official_kat/acvp/SHA256SUMS"),
        fixtures={p.name: sha(p) for p in paths}, roundtrip_verified=True)
    paths += [ROOT / item["path"] for item in sources]
    paths += [ROOT / "vectors/official_kat/acvp/SHA256SUMS",
              ROOT / "scripts/kat/package_mlkem.py", ROOT / "scripts/kat/validate_acvp_json.py"]
    return paths, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-dir", type=Path, default=TOOLS)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--board", action="store_true",
                       help="Build self-checking three-case board firmware in an independent directory")
    modes.add_argument("--ps", action="store_true",
                       help="Build one-case PS shared-RAM firmware without embedded vectors or answers")
    args = parser.parse_args()
    src = ROOT / "firmware/mlkem1024_keccak"
    common = ROOT / "firmware/mlkem_baseline"
    suite = ROOT / "firmware/mlkem_suite"
    vendor = ROOT / "third_party/mlkem-native"
    lib = vendor / "mlkem"
    fixtures = ROOT / "tb/software/mlkem1024_suite"
    mode = "ps" if args.ps else "board" if args.board else "kat"
    linker = src / ("ps_link.ld" if args.ps else "link.ld")
    main_source = src / "ps_kat.c" if args.ps else src / "board_kat.c" if args.board else suite / "kat_suite.c"
    out = ROOT / "build/keccak_cpu" / mode
    evidence = ROOT / "results/keccak_cpu" / mode
    manifest = json.loads((vendor / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        require(sha(vendor / item["path"]) == item["sha256"],
                "Vendor changed: " + item["path"])
    cases = json.loads((fixtures / "cases.json").read_text(encoding="utf-8"))
    require(len(cases["cases"]) == 145, "Expected frozen 145-case K4 fixture")

    def tool(name):
        path = args.tool_dir / f"riscv64-unknown-elf-{name}.exe"
        require(path.is_file(), f"Missing tool: {path}")
        return path

    def run(command):
        result = subprocess.run(list(map(str, command)), cwd=ROOT,
                                capture_output=True, text=True)
        require(result.returncode == 0, f"Command failed: {command}\n{result.stdout}{result.stderr}")
        return result.stdout

    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    board_files, board_record = board_vectors(out) if args.board else ([], None)
    sources = [common / "startup.S", main_source, common / "runtime.c",
               src / "keccak_mmio.c", src / "fips202_hw.c"]
    sources += sorted((lib / "src").glob("*.c"))
    require(not any("fips202" in path.parts for path in sources), "Software FIPS 202 included")
    source_files = set(sources + [Path(__file__).resolve(), common / "kat_protocol.h",
        linker, src / "kat_config.h", src / "keccak_mmio.h",
        src / "fips202_hw.h", src / "fips202x4_hw.h", vendor / "SOURCE_MANIFEST.json"])
    source_files.update(vendor / item["path"] for item in manifest["files"])
    source_files.update(fixtures / name for name in
        ["cases.json", "mlkem1024_input.mem", "mlkem1024_expected.mem"])
    source_files.update(board_files)
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(source_files)}
    flags = ["-march=rv32im", "-mabi=ilp32", "-O3", "-std=c11", "-ffreestanding",
        "-fno-builtin", "-fno-pic", "-msmall-data-limit=0", "-ffunction-sections",
        "-fdata-sections", "-fno-tree-loop-distribute-patterns", "-fstack-usage",
        "-Wall", "-Wextra", "-Werror", "-I", str(src), "-I", str(common),
        "-I", str(lib), "-DMLK_CONFIG_FILE=<kat_config.h>"]
    if args.board:
        flags += ["-I", str(out)]
    commands, logs, objects = [], [], []
    for path in sources:
        obj = out / (path.stem + ".o")
        command = [tool("gcc"), *flags, "-c", path, "-o", obj]
        logs.append(run(command))
        commands.append(list(map(str, command)))
        objects.append(obj)
    elf, binary, image = out / f"{mode}.elf", out / f"{mode}.bin", out / f"{mode}.mem"
    command = [tool("gcc"), *flags, "-nostdlib", "-nostartfiles",
        "-Wl,--build-id=none", "-Wl,--gc-sections", f"-Wl,-Map,{out / (mode + '.map')}",
        "-T", linker, *objects, "-lgcc", "-o", elf]
    logs.append(run(command))
    commands.append(list(map(str, command)))
    (out / "build.txt").write_text("\n".join(logs), encoding="utf-8")
    symbols_text = run([tool("nm"), "-n", elf])
    symbols = {m[3]: int(m[1], 16) for line in symbols_text.splitlines()
               if (m := re.fullmatch(r"([0-9a-fA-F]+)\s+(\w)\s+(\S+)", line))}
    require(not run([tool("nm"), "-u", elf]).strip(), "Unresolved symbols")
    require(symbols["_start"] == 0 and symbols["__image_end"] <= symbols["__stack_bottom"],
            "Firmware/stack overlap")
    if args.ps:
        for name, address in {"__ps_input_start": 0x10000, "__ps_input_end": 0x12000,
                              "__ps_output_start": 0x12000, "__ps_output_end": 0x14000,
                              "__stack_bottom": 0x17ff0, "__stack_top": 0x1fff0}.items():
            require(symbols.get(name) == address, "PS memory layout changed: " + name)
        require(symbols["__image_end"] <= symbols["__ps_input_start"], "PS firmware/shared input overlap")
        require(not any(name.startswith("board_") for name in symbols), "Embedded board vectors in PS firmware")
    for api in ["keypair_derand", "enc_derand", "dec", "check_pk", "check_sk"]:
        require("pico_mlkem1024_" + api in symbols, "Missing ML-KEM API: " + api)
    needed = ["sha3_256", "sha3_512", "shake256", "shake128x4_absorb_once",
              "shake128x4_squeezeblocks", "shake128x4_init", "shake128x4_release"]
    provider_symbols = ["pico_mlkem1024_" + name for name in needed]
    provider_nm = run([tool("nm"), "--defined-only", out / "fips202_hw.o"])
    for symbol in provider_symbols:
        require(symbol in symbols and re.search(r"\b" + re.escape(symbol) + r"$", provider_nm, re.M),
                "Missing hardware provider symbol: " + symbol)
    require("keccak_mmio_run" in symbols, "MMIO path not linked")
    forbidden = [name for name in symbols
                 if re.search(r"keccakf1600|keccak_absorb|keccak_squeeze|KeccakF1600", name)]
    require(not forbidden, "Software Keccak present: " + str(forbidden))
    dump = run([tool("objdump"), "-d", elf])
    attrs = run([tool("readelf"), "-A", elf])
    require("rv32i" in attrs and "m2p0" in attrs, "Wrong ISA")
    size = run([tool("size"), "-A", elf])
    for name, data in [("disassembly.txt", dump), ("attributes.txt", attrs),
                       ("symbols.txt", symbols_text), ("size.txt", size),
                       ("provider_symbols.txt", provider_nm)]:
        (out / name).write_text(data, encoding="ascii")
    run([tool("objcopy"), "-O", "binary", elf, binary])
    data = binary.read_bytes()
    require(len(data) <= symbols["__ps_input_start"] if args.ps else len(data) <= symbols["__stack_bottom"],
            "Binary exceeds RAM reservation")
    padded = data + bytes(131072-len(data))
    image.write_text("".join(f"{int.from_bytes(padded[i:i+4], 'little'):08x}\n"
        for i in range(0, len(padded), 4)), encoding="ascii", newline="\n")
    libgcc = Path(run([tool("gcc"), "-march=rv32im", "-mabi=ilp32",
                      "-print-libgcc-file-name"]).strip())
    for name, digest in before.items():
        require(sha(ROOT / name) == digest, "Build input changed: " + name)
    stack_frames = "\n".join(path.read_text(encoding="ascii")
        for path in sorted(out.glob("*.su")))
    (out / "stack_frames.txt").write_text(stack_frames, encoding="ascii")
    record = dict(status="BUILD_ONLY", parameter_set=1024, isa="rv32im",
        scope=("PS-driven single-case K4 firmware; PS compares official expected bytes and API returns; RTL results pending"
               if args.ps else "Standalone three-case official K4 board firmware; CPU compares expected bytes and return codes; RTL results pending"
               if args.board else "Official K4 KAT firmware using hardware-only FIPS 202; RTL results pending"),
        compiler=run([tool("gcc"), "--version"]).splitlines()[0],
        compiler_sha256=sha(tool("gcc")), libgcc_path=str(libgcc), libgcc_sha256=sha(libgcc),
        ram_bytes=131072, stack_reserved=32768, binary_bytes=len(data),
        static_end=symbols["__image_end"], stack_top=symbols["__stack_top"],
        stack_bottom=symbols["__stack_bottom"],
        firmware=image.relative_to(ROOT).as_posix(), firmware_sha256=sha(image),
        elf_sha256=sha(elf), source_sha256=before, flags=flags, commands=commands,
        compiled_sources=[p.relative_to(ROOT).as_posix() for p in sources],
        provider_symbols=provider_symbols, excluded_software_fips202=True,
        software_keccak_symbols=forbidden, mlkem_native_commit=manifest["source_commit"],
        linker_sha256=sha(linker),
        provider_limits=dict(shake128_pending_input_bytes=34, input_bytes=2048,
            output_bytes=4096, reentrant=False, sha128x4_independent_contexts=True,
            first_squeeze="combined HASH", subsequent_squeeze="SQUEEZE",
            cpu_zeroization=True, accelerator_bram_erasure=False))
    if args.board:
        record.update(board_subset=board_record, case_count=3,
                      generated_sha256={name: sha(out / name) for name in
                          ("board.mem", "board_input.mem", "board_expected.mem", "board_vectors.h")},
                      self_checking=True, host_mailbox=False,
                      protocol="Existing KAT debug events and streams, without REQUEST/mailbox",
                      completion="PASS or FAIL then infinite nop; reset clears BSS via startup")
    if args.ps:
        record.update(case_count=1, supported_operations=[1, 2, 3, 4, 5, 6],
                      self_checking=False, host_mailbox=False, embedded_vectors=False,
                      expected_values_in_firmware=False,
                      shared_ram=dict(input_address=0x10000, input_bytes=8192,
                                      output_address=0x12000, output_bytes=8192,
                                      firmware_limit=0x10000, unused_gap=[0x14000, 0x17ff0]),
                      protocol=dict(input="pack_fixture([case with local index 0], 1024, False)",
                                    input_header_words=8, input_meta_words=12,
                                    output_header=["magic=0x4b34524f", "ABI=1", "operation",
                                                   "int32 API return", "out1 bytes", "out2 bytes",
                                                   "raw API cycles", "empty-bracket cycles"],
                                    output_payload="out1 || out2; little-endian 32-bit words",
                                    completion="KATP commits transport only; PS compares official bytes and return; KATF is protocol failure"),
                      completion="Store fence before PASS, then infinite nop; PS resets CPU for each case; startup clears BSS only")
    (evidence / "build.json").write_text(json.dumps(record, indent=2)+"\n",
                                         encoding="utf-8", newline="\n")
    print(f"KECCAK_KAT_BUILD_PASS image_bytes={len(data)} static_end={symbols['__image_end']} "
          f"stack_reserved=32768 no_software_keccak=1 firmware={image}")


if __name__ == "__main__":
    main()
