"""Run one/all ML-KEM-512 RTL suites with frozen input hashes and quiet logs."""
from pathlib import Path
import argparse
import concurrent.futures
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ('rv32i', 'rv32im_iterative', 'rv32im_fast')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(config, vivado):
    results = ROOT / 'results/official_baseline/mlkem512' / config
    results.mkdir(parents=True, exist_ok=True)
    build = ROOT / 'build/mlkem512_suite'
    build.mkdir(parents=True, exist_ok=True)
    inputs = [ROOT / name for name in (
        'rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
        'tb/software/tb_mlkem512_suite.sv', 'scripts/mlkem512_suite/run.tcl',
        'scripts/mlkem512_suite/sim.tcl', 'scripts/mlkem512_suite/run.py',
        'results/official_baseline/mlkem512/build_manifest.json')]
    inputs += list((ROOT / 'tb/software/mlkem512_suite').glob('*'))
    inputs += list((ROOT / 'firmware/images/mlkem512_suite').glob('*.mem'))
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in inputs if p.is_file()}
    command = [str(vivado), '-mode', 'batch', '-source', 'scripts/mlkem512_suite/run.tcl',
               '-log', str(build / (config + '.log')),
               '-journal', str(build / (config + '.jou')), '-tclargs', config]
    record = dict(config=config, simulator='Vivado/XSim 2024.2', ram_bytes=65536,
                  command=command, input_sha256=hashes)
    (results / 'run_inputs.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    console = build / (config + '_console.txt')
    with console.open('w', encoding='utf-8') as stream:
        code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
    if code:
        raise RuntimeError(f'{config}: Vivado failed ({code}); inspect {console}')
    for name, wanted in hashes.items():
        if digest(ROOT / name) != wanted:
            raise RuntimeError(f'Input changed during {config}: {name}')
    print(f'MLKEM512_RUN_PASS config={config}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', choices=CONFIGS)
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    args = parser.parse_args()
    configs = [args.config] if args.config else list(CONFIGS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(configs)) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, c, args.vivado) for c in configs]):
            future.result()


if __name__ == '__main__':
    main()
