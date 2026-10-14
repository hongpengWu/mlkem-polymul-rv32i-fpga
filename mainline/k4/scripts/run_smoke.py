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

from paths import ROOT, K4, BUILD as K4_BUILD, tool_path, repository_path, selected_hls_run, verified_hls, hls_input_pairs, verify_hls_snapshot


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, value):
    p.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hls-run', type=Path, default=selected_hls_run())
    parser.add_argument('--run-root', type=Path, default=K4_BUILD / 'smoke_runs')
    parser.add_argument('--evidence-dir', type=Path, default=ROOT / 'results/k4/smoke',
                        help='Evidence archive root for successful runs')
    parser.add_argument('--vivado', type=Path, help='Vivado executable (or PQC_VIVADO/PATH)')
    args = parser.parse_args()
    args.vivado = tool_path('vivado', args.vivado)
    args.run_root = repository_path(args.run_root)
    args.evidence_dir = repository_path(args.evidence_dir)
    # Independent runs never overwrite a locked snapshot. Also serialize the entry point.
    guard = ROOT / 'build/k4/.smoke_running'
    guard.parent.mkdir(parents=True, exist_ok=True)
    if not args.vivado.is_file():
        raise RuntimeError('Missing Vivado')
    args.hls_run, selection = verified_hls(args.hls_run)
    build_file = K4_BUILD / 'smoke/build.json'
    build = json.loads(build_file.read_text())
    for name, digest in build['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError('Stale firmware build; rebuild smoke: ' + name)
    for name, digest in build['generated_sha256'].items():
        if sha(ROOT / 'build/k4/smoke' / name) != digest:
            raise RuntimeError('Generated firmware/fixture changed: ' + name)
    with guard.open('x') as f:
        f.write(str(os.getpid()))
    run = args.run_root / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    try:
        run.mkdir(parents=True)
        pairs = []
        for name in ('rtl/cpu/picorv32.v', 'mainline/k4/rtl/keccak_mmio_adapter.sv',
                     'mainline/k4/rtl/mlkem1024_keccak_system.sv'):
            pairs.append((ROOT / name, Path('rtl') / Path(name).name))
        pairs.append((ROOT / 'mainline/k4/tb/tb_mlkem1024_keccak_cpu_smoke.sv', Path('tb/tb_mlkem1024_keccak_cpu_smoke.sv')))
        pairs.append((K4 / 'flow.tcl', Path('run_smoke.tcl')))
        pairs.append((build_file, Path('build.json')))
        for name in ('smoke.mem', 'expected.mem', 'meta.mem'):
            pairs.append((ROOT / 'build/k4/smoke' / name, Path('fixtures') / name))
        pairs += [(source, Path(name)) for source, name in hls_input_pairs(args.hls_run, selection)]
        selection_file = run / 'hls_selection.json'
        dump(selection_file, selection)
        pairs.append((selection_file, Path('hls_selection.json')))
        if len([p for p, _ in pairs if p.suffix == '.v']) < 2:
            raise RuntimeError('Missing generated HLS RTL')
        frozen = {}
        for source, relative in pairs:
            target = run / 'snapshot' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            frozen[relative.as_posix()] = dict(source=str(source), sha256=sha(target))
        verify_hls_snapshot(run / 'snapshot', selection)
        cmd = [str(args.vivado), '-mode', 'batch', '-source', str(run / 'snapshot/run_smoke.tcl'), '-tclargs', '--worker', 'smoke', str(run)]
        dump(run / 'manifest.json', dict(started_utc=datetime.now(timezone.utc).isoformat(),
             command=cmd, hls_run=str(args.hls_run), inputs=frozen, ram_bytes=131072, stack_bytes=32768))
        print('KECCAK_CPU_RUN_DIR=' + str(run), flush=True)
        try:
            with (run / 'console.txt').open('w') as log:
                result = subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT)
        except BaseException as exc:
            result = None
            dump(run / 'result.json', dict(passed=False, exit_code=None,
                 completed_utc=datetime.now(timezone.utc).isoformat(),
                 error='Interrupted: ' + repr(exc),
                 scope='PicoRV32 fast CPU plus Keccak local smoke, not official K4 KAT'))
            raise
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
        evidence = args.evidence_dir / run.name
        evidence.mkdir(parents=True, exist_ok=False)
        for name in ('manifest.json', 'result.json', 'simulate.txt', 'console.txt'):
            shutil.copy2(run / name, evidence / name)
        print(log[-2500:])
    except BaseException as exc:
        if run.exists() and not (run / 'result.json').exists():
            dump(run / 'result.json', dict(
                passed=False, exit_code=None,
                completed_utc=datetime.now(timezone.utc).isoformat(),
                error='Interrupted before completion: ' + repr(exc),
                scope='PicoRV32 fast CPU plus Keccak local smoke, not official K4 KAT'))
        raise
    finally:
        guard.unlink()


if __name__ == '__main__':
    main()
