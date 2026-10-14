"""Run parameterized CPU-only ML-KEM suites in Vivado/XSim 2024.2."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ('rv32i', 'rv32im_iterative', 'rv32im_fast')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(level, config, vivado):
    tag = f'mlkem{level}'
    results = ROOT / 'results/official_baseline' / tag / config
    results.mkdir(parents=True, exist_ok=True)
    build = ROOT / 'build' / f'{tag}_suite'; build.mkdir(parents=True, exist_ok=True)
    inputs = [ROOT / name for name in (
        'rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
        'tb/software/tb_mlkem_suite.sv', 'scripts/mlkem_suite/run.tcl',
        'scripts/mlkem_suite/sim.tcl', 'scripts/mlkem_suite/run.py',
        f'firmware/images/{tag}_suite/{"rv32i" if config == "rv32i" else "rv32im"}.mem',
    )]
    inputs += list((ROOT / f'tb/software/{tag}_suite').glob('*'))
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in inputs if p.is_file()}
    command = [str(vivado), '-mode', 'batch', '-source', 'scripts/mlkem_suite/run.tcl',
               '-log', str(build / f'{config}.log'), '-journal', str(build / f'{config}.jou'),
               '-tclargs', str(level), config]
    ram_bytes = 65536 if level == 512 else 131072
    record = dict(parameter_set=level, config=config, simulator='Vivado/XSim 2024.2',
                  ram_bytes=ram_bytes, stack_bytes=16384 if level == 512 else 32768,
                  command=command, input_sha256=hashes)
    (results / 'run_inputs.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    console = build / f'{config}_console.txt'
    with console.open('w', encoding='utf-8') as stream:
        code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
    if code:
        raise RuntimeError(f'{tag} {config}: Vivado failed ({code}); inspect {console}')
    for name, wanted in hashes.items():
        if digest(ROOT / name) != wanted:
            raise RuntimeError(f'Input changed during {tag} {config}: {name}')
    print(f'MLKEM{level}_RUN_PASS config={config}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameter-set', type=int, required=True, choices=(768, 1024))
    parser.add_argument('--config', choices=CONFIGS)
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    args = parser.parse_args()
    configs = [args.config] if args.config else list(CONFIGS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(configs)) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, args.parameter_set, c, args.vivado) for c in configs]):
            future.result()


if __name__ == '__main__':
    main()
