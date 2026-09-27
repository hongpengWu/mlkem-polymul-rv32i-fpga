"""Implement both verified K4 systems at the same OOC boundary and constraints.

Freezes the actual official-KAT RTL/firmware into short, unique run directories.
No baseline files or RTL are changed; generated projects/checkpoints stay outside
Git. This measures the complete CPU/RAM/accelerator block, not board IO closure.
"""
import argparse
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from run_kat import ROOT, sha, dump, tool_guard

RESULTS = ROOT / 'results/keccak_cpu/system_impl'


def prepare(variant, run):
    pairs = []
    if variant == 'keccak':
        proof = ROOT / 'results/keccak_cpu/kat/batches/pilot_000_001_115/20260927_171430_546316/manifest.json'
        manifest = json.loads(proof.read_text())
        snapshot = Path(manifest['run_dir']) / 'snapshot'
        names = [name for name in manifest['inputs'] if name.startswith(('rtl/', 'hls/'))]
        names.append('fixtures/mlkem1024.mem')
        for name in names:
            source = snapshot / name
            if sha(source) != manifest['inputs'][name]['sha256']:
                raise ValueError('Verified KAT input changed: ' + name)
            relative = 'firmware.mem' if name.startswith('fixtures/') else name
            pairs.append((source, relative))
    else:
        proof = ROOT / 'results/official_baseline/mlkem1024/batches/rv32im_fast/batch_000_007/run_inputs.json'
        manifest = json.loads(proof.read_text())
        for name in ('rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
                     'firmware/images/mlkem1024_suite/rv32im.mem'):
            source = ROOT / name
            if sha(source) != manifest['input_sha256'][name]:
                raise ValueError('CPU-only KAT input changed: ' + name)
            relative = 'firmware.mem' if name.endswith('.mem') else 'rtl/' + source.name
            pairs.append((source, relative))
    pairs += [(Path(__file__).with_suffix('.tcl'), 'implement_system.tcl'),
              (Path(__file__), 'implement_system.py'),
              (ROOT / 'constraints/mlkem1024_system_ooc.xdc', 'system.xdc'),
              (proof, 'kat_provenance.json')]
    inputs = {}
    for source, name in pairs:
        target = run / 'snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inputs[name] = dict(source=str(source), sha256=sha(target))
    return inputs


def resources(report):
    text = report.read_text(errors='replace')
    values = {}
    for key, label in [('lut', 'Slice LUTs'), ('ff', 'Slice Registers'),
                       ('bram36_tiles', 'Block RAM Tile'), ('dsp', 'DSPs')]:
        match = re.search(r'^\|\s*' + re.escape(label) + r'\*?\s*\|\s*([\d,.]+)\s*\|', text, re.M)
        if not match:
            raise ValueError('Missing resource row: ' + label)
        values[key] = float(match[1].replace(',', ''))
    return values


def run_one(args, variant, group):
    tool_guard()
    run = args.run_root / group / variant
    run.mkdir(parents=True, exist_ok=False)
    inputs = prepare(variant, run)
    cmd = [str(args.vivado), '-mode', 'batch', '-source', str(run / 'snapshot/implement_system.tcl'),
           '-tclargs', str(run), variant]
    manifest = dict(variant=variant, run_dir=str(run), started_utc=datetime.now(timezone.utc).isoformat(),
        inputs=inputs, command=cmd, part='xc7z020clg400-1', period_ns=10.0, ram_bytes=131072,
        cpu='rv32im_fast', max_threads=8, scope='Complete system OOC; assumed 2ns synchronous IO budget; not board implementation')
    dump(run / 'manifest.json', manifest)
    dump(ROOT / 'build/keccak_cpu/implementation_progress.json', dict(status='running', variant=variant,
         run_dir=str(run), pid=os.getpid(), console=str(run / 'console.txt')))
    print(f'SYSTEM_IMPL_START variant={variant} run={run}', flush=True)
    started = time.monotonic()
    with (run / 'console.txt').open('w', encoding='utf-8') as log:
        process = subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT)
    result = dict(exit_code=process.returncode, elapsed_seconds=time.monotonic()-started,
        completed_utc=datetime.now(timezone.utc).isoformat(), manifest_sha256=sha(run / 'manifest.json'),
        implementation_completed=False, timing_met=False)
    try:
        for name, info in inputs.items():
            if sha(run / 'snapshot' / name) != info['sha256']:
                raise ValueError('Frozen implementation input changed: ' + name)
        result['metrics'] = json.loads((run / 'reports/metrics.json').read_text())
        result['resources'] = resources(run / 'reports/utilization.rpt')
        result['checkpoint_sha256'] = {name: sha(run / name) for name in ('synth.dcp', 'routed.dcp')}
        result['implementation_completed'] = True
        result['timing_met'] = result['metrics']['timing_met']
        if process.returncode:
            raise ValueError('Vivado exit=' + str(process.returncode) + '; inspect retained reports')
    except Exception as exc:
        result['error'] = str(exc)
    evidence = RESULTS / group / variant
    evidence.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'console.txt'):
        shutil.copy2(run / name, evidence / name)
    if (run / 'reports').exists():
        shutil.copytree(run / 'reports', evidence / 'reports')
    result['report_sha256'] = {p.relative_to(evidence).as_posix(): sha(p)
                               for p in sorted(evidence.rglob('*')) if p.is_file()}
    dump(run / 'result.json', result)
    dump(evidence / 'result.json', result)
    print(f'SYSTEM_IMPL_END {variant} completed={result["implementation_completed"]} timing_met={result["timing_met"]}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, default=Path('E:/hls/k4sys'))
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    args = parser.parse_args()
    if not args.vivado.is_file():
        raise ValueError('Vivado unavailable')
    guard_path = ROOT / 'build/keccak_cpu/implementation.lock'
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    with guard_path.open('a+b') as guard:
        guard.seek(0)
        if not guard.read(1):
            guard.write(b'0'); guard.flush()
        guard.seek(0)
        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        group = datetime.now().strftime('%Y%m%d_%H%M%S')
        results = {}
        for variant in ('keccak', 'cpu_only'):
            results[variant] = run_one(args, variant, group)
        dump(RESULTS / group / 'comparison.json', results)
        dump(ROOT / 'build/keccak_cpu/implementation_progress.json', dict(status='finished', group=group,
             results=str(RESULTS / group / 'comparison.json')))
        print('SYSTEM_IMPL_FINISHED ' + str(RESULTS / group / 'comparison.json'), flush=True)


if __name__ == '__main__':
    main()
