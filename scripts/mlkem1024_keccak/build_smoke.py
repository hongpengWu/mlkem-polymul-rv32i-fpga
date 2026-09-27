"""Build RV32IM Keccak MMIO smoke; hashlib expectations stay outside firmware."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CALLS = 10


def packed(data):
    data += bytes((-len(data)) % 4)
    return [int.from_bytes(data[i:i+4], "little") for i in range(0, len(data), 4)]


def memory(path, words):
    path.write_text("".join(f"{word & 0xffffffff:08x}\n" for word in words),
                    encoding="ascii", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-dir", type=Path, default=Path(
        "E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin"))
    args = parser.parse_args()
    out = ROOT / "build/keccak_cpu/smoke"
    out.mkdir(parents=True, exist_ok=True)
    src = ROOT / "firmware/mlkem1024_keccak"
    # Deterministic messages model public K4 input lengths; they are local
    # FIPS 202 component tests, not NIST ACVP KEM test vectors.
    payloads = [bytes((i*37 + i//7 + seed) & 255 for i in range(length))
                for length, seed in [(1568, 11), (1600, 29), (64, 53),
                                     (34, 71), (33, 97)]]
    # name, input id/-1, input bytes, output bytes, mode, command, context id
    calls = [
        ("H_ek_1568", 0, 1568, 32, 2, 0, 0),
        ("J_z_ciphertext_1600", 1, 1600, 32, 1, 0, 0),
        ("G_64", 2, 64, 64, 3, 0, 0),
        ("XOF_first_13", 3, 34, 13, 0, 0, 0),
        ("interleaved_SHAKE256_7", 4, 33, 7, 1, 0, 1),
        ("XOF_continue_491", -1, 0, 491, 0, 1, 0),
        ("XOF_continue_168", -1, 0, 168, 0, 1, 0),
        ("clear_context", -1, 0, 0, 0, 2, 0),
        ("reject_squeeze_after_clear", -1, 0, 17, 0, 1, 0),
        ("reject_SHA3_output_length", -1, 0, 31, 2, 0, 1),
    ]
    assert len(calls) == CALLS
    xof = hashlib.shake_128(payloads[3]).digest(672)
    expected_bytes = [hashlib.sha3_256(payloads[0]).digest(),
                      hashlib.shake_256(payloads[1]).digest(32),
                      hashlib.sha3_512(payloads[2]).digest(), xof[:13],
                      hashlib.shake_256(payloads[4]).digest(7),
                      xof[13:504], xof[504:672], b"", None, None]
    returns = [0]*8 + [-2, -1]
    declarations = []
    for index, payload in enumerate(payloads):
        words = packed(payload)
        declarations.append("static const uint32_t input_%d[%d] = {%s};" %
            (index, len(words), ",".join(f"0x{value:08x}u" for value in words)))
    declarations.extend([
        f"#define SMOKE_CALLS {CALLS}u",
        "struct smoke_call { const uint32_t *input; uint32_t input_len, output_len, mode, command, context_id; };",
        "static const struct smoke_call smoke_calls[SMOKE_CALLS] = {"])
    expected, metadata, descriptions = [], [], []
    cumulative_writes = cumulative_reads = 0
    for index, (name, payload, input_len, output_len, mode, command, context) in enumerate(calls):
        declarations.append("{%s,%du,%du,%du,%du,%du}," %
            (f"input_{payload}" if payload >= 0 else "0", input_len, output_len, mode, command, context))
        output_words = (output_len+3)//4
        wanted = packed(expected_bytes[index]) if expected_bytes[index] is not None else [0xa5a5a5a5]*output_words
        assert len(wanted) == output_words
        cumulative_writes += 52 + (input_len+3)//4
        cumulative_reads += 52 + (output_words if returns[index] == 0 else 0)
        metadata += [len(expected), output_words, returns[index] & 0xffffffff,
                     cumulative_writes, cumulative_reads, output_len, input_len,
                     mode | (command << 8)]
        expected += wanted
        descriptions.append(dict(index=index, name=name, input_bytes=input_len,
            output_bytes=output_len, mode=mode, command=command, context=context,
            expected_return=returns[index], expected_words=output_words))
    declarations.append("};\n")
    header = out / "smoke_inputs.h"
    header.write_text("\n".join(declarations), encoding="ascii", newline="\n")
    memory(out / "expected.mem", expected)
    memory(out / "meta.mem", metadata)
    assert len(expected) == 216 and len(metadata) == 80

    def tool(name):
        return args.tool_dir / f"riscv64-unknown-elf-{name}.exe"

    def run(command):
        result = subprocess.run(list(map(str, command)), cwd=ROOT,
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    startup = ROOT / "firmware/mlkem_baseline/startup.S"
    elf, binary = out / "smoke.elf", out / "smoke.bin"
    command = [tool("gcc"), "-march=rv32im", "-mabi=ilp32", "-O3", "-std=c11",
        "-ffreestanding", "-fno-builtin", "-fno-pic", "-msmall-data-limit=0",
        "-Wall", "-Wextra", "-Werror", "-nostdlib", "-nostartfiles",
        "-Wl,--build-id=none", f"-Wl,-Map,{out / 'smoke.map'}",
        "-I", out, "-I", src, "-T", src / "link.ld", startup,
        src / "smoke.c", src / "keccak_mmio.c", "-lgcc", "-o", elf]
    run(command)
    run([tool("objcopy"), "-O", "binary", elf, binary])
    data = binary.read_bytes()
    if len(data) > 128*1024 - 32768 - 16:
        raise RuntimeError("Firmware binary overlaps reserved stack")
    memory(out / "smoke.mem", packed(data + bytes(128*1024-len(data))))
    (out / "disassembly.txt").write_text(run([tool("objdump"), "-d", elf]), encoding="ascii")
    (out / "size.txt").write_text(run([tool("size"), elf]), encoding="ascii")
    source_files = [startup, src / "link.ld", src / "keccak_mmio.h",
        src / "keccak_mmio.c", src / "smoke.c", Path(__file__).resolve(),
        ROOT / "tb/accelerator/tb_mlkem1024_keccak_cpu_smoke.sv"]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = ROOT / "results/keccak_cpu/smoke"
    evidence.mkdir(parents=True, exist_ok=True)
    manifest = dict(scope="Local FIPS 202 CPU-to-Keccak MMIO smoke; not official K4 KEM execution",
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        isa="rv32im", ram_bytes=128*1024, reserved_stack_bytes=32768,
        binary_bytes=len(data), calls=descriptions, expected_words=len(expected),
        compiler=run([tool("gcc"), "--version"]).splitlines()[0],
        command=list(map(str, command)),
        firmware_sha256=digest(out / "smoke.mem"),
        source_sha256={path.relative_to(ROOT).as_posix(): digest(path) for path in source_files},
        generated_sha256={path.name: digest(path) for path in
            [header, out / "smoke.mem", out / "expected.mem", out / "meta.mem"]})
    (evidence / "build.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(f"KECCAK_CPU_SMOKE_BUILD_PASS calls={CALLS} words={len(expected)} image_bytes={len(data)} out={out}")


if __name__ == "__main__":
    main()
