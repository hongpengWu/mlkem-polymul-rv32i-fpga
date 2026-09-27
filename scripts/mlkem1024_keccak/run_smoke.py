"""Run a frozen, unique Pico+Keccak RTL smoke; preserve failed attempts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, value):
    p.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hls-run', type=Path, default=Path('E:/hls/k4_io1/opt02'))
    parser.add_argument('--run-root', type=Path, default=Path('E:/hls/k4cpu'))
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    args = parser.parse_args()
    # Independent runs never overwrite a locked snapshot. Also serialize the entry point.
    guard = ROOT / 'build/keccak_cpu/.smoke_running'
    guard.parent.mkdir(parents=True, exist_ok=True)
    if not args.vivado.is_file():
        raise RuntimeError('Missing Vivado')
    manifest = json.loads((args.hls_run / 'manifest.json').read_text())
    metrics = json.loads((args.hls_run / 'reports/metrics.json').read_text())
    if not metrics['functional_hls_flow_passed'] or manifest['config']['io_opt'] != 1:
        raise RuntimeError('Require functionally verified optimized HLS run')
    for name, digest in manifest['input_sha256'].items():
        if sha(ROOT / 'hls/mlkem1024_keccak' / name) != digest:
            raise RuntimeError('HLS source/TB differs from selected run: ' + name)
    selected = json.loads((ROOT / 'results/hls/mlkem1024_keccak/rtl_equivalence.json').read_text())['selected']
    for name, info in selected.items():
        if sha(args.hls_run / 'p/sol1/syn/verilog' / name) != info['raw_sha256']:
            raise RuntimeError('Generated RTL differs from verified selection: ' + name)
    build_file = ROOT / 'results/keccak_cpu/smoke/build.json'
    build = json.loads(build_file.read_text())
    for name, digest in build['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError('Stale firmware build; rebuild smoke: ' + name)
    for name, digest in build['generated_sha256'].items():
        if sha(ROOT / 'build/keccak_cpu/smoke' / name) != digest:
            raise RuntimeError('Generated firmware/fixture changed: ' + name)
    with guard.open('x') as f:
        f.write(str(os.getpid()))
    run = args.run_root / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    try:
        run.mkdir(parents=True)
        pairs = []
        for name in ('rtl/cpu/picorv32.v', 'rtl/accelerator/keccak_mmio_adapter.sv',
                     'rtl/accelerator/mlkem1024_keccak_system.sv'):
            pairs.append((ROOT / name, Path('rtl') / Path(name).name))
        pairs.append((ROOT / 'tb/accelerator/tb_mlkem1024_keccak_cpu_smoke.sv', Path('tb/tb_mlkem1024_keccak_cpu_smoke.sv')))
        pairs.append((Path(__file__).with_suffix('.tcl'), Path('run_smoke.tcl')))
        pairs.append((build_file, Path('build.json')))
        for name in ('smoke.mem', 'expected.mem', 'meta.mem'):
            pairs.append((ROOT / 'build/keccak_cpu/smoke' / name, Path('fixtures') / name))
        pairs += [(p, Path('hls') / p.name) for p in sorted((args.hls_run / 'p/sol1/syn/verilog').iterdir()) if p.suffix in ('.v', '.dat')]
        if len([p for p, _ in pairs if p.suffix == '.v']) < 2:
            raise RuntimeError('Missing generated HLS RTL')
        frozen = {}
        for source, relative in pairs:
            target = run / 'snapshot' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            frozen[relative.as_posix()] = dict(source=str(source), sha256=sha(target))
        cmd = [str(args.vivado), '-mode', 'batch', '-source', str(run / 'snapshot/run_smoke.tcl'), '-tclargs', str(run)]
        dump(run / 'manifest.json', dict(started_utc=datetime.now(timezone.utc).isoformat(),
             command=cmd, hls_run=str(args.hls_run), inputs=frozen, ram_bytes=131072, stack_bytes=32768))
        print('KECCAK_CPU_RUN_DIR=' + str(run), flush=True)
        with (run / 'console.txt').open('w') as log:
            result = subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT)
        log = (run / 'simulate.txt').read_text(errors='replace') if (run / 'simulate.txt').exists() else ''
        final = 'KECCAK_CPU_SMOKE_PASS calls=10 words=216 hls_starts=10 hls_dones=10'
        passed = result.returncode == 0 and final in log and not re.search('fatal:|ERROR:|KECCAK_CPU_SMOKE_FAIL', log, re.I)
        for name, info in frozen.items():
            if sha(run / 'snapshot' / name) != info['sha256']:
                passed = False
        dump(run / 'result.json', dict(passed=passed, exit_code=result.returncode,
             completed_utc=datetime.now(timezone.utc).isoformat(), scope='PicoRV32 fast CPU plus Keccak local smoke, not official K4 KAT'))
        if not passed:
            raise RuntimeError('Failed attempt retained at ' + str(run))
        evidence = ROOT / 'results/keccak_cpu/smoke' / run.name
        evidence.mkdir(parents=True, exist_ok=False)
        for name in ('manifest.json', 'result.json', 'simulate.txt', 'console.txt'):
            shutil.copy2(run / name, evidence / name)
        print(log[-2500:])
    finally:
        guard.unlink()


if __name__ == '__main__':
    main()
