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
import xml.etree.ElementTree as ET
import zipfile

from run_kat import ROOT, sha, dump, tool_guard

RESULTS = ROOT / 'results/keccak_cpu/system_impl'


def prepare(variant, run, keccak_source):
    pairs = []
    if variant == 'keccak':
        proof = ROOT / 'results/keccak_cpu/kat/batches/pilot_000_001_115/20260927_171430_546316/manifest.json'
        manifest = json.loads(proof.read_text())
        snapshot = Path(manifest['run_dir']) / 'snapshot'
        names = [name for name in manifest['inputs'] if name.startswith('hls/')]
        names.append('fixtures/mlkem1024.mem')
        for name in names:
            source = snapshot / name
            if sha(source) != manifest['inputs'][name]['sha256']:
                raise ValueError('Verified KAT input changed: ' + name)
            relative = 'firmware.mem' if name.startswith('fixtures/') else name
            pairs.append((source, relative))
        if keccak_source == 'current':
            pairs[:0] = [
                (ROOT / 'rtl/cpu/picorv32.v', 'rtl/picorv32.v'),
                (ROOT / 'rtl/accelerator/keccak_mmio_adapter.sv', 'rtl/keccak_mmio_adapter.sv'),
                (ROOT / 'rtl/accelerator/mlkem1024_keccak_system.sv', 'rtl/mlkem1024_keccak_system.sv'),
            ]
        else:
            for name in manifest['inputs']:
                if name.startswith('rtl/'):
                    source = snapshot / name
                    if sha(source) != manifest['inputs'][name]['sha256']:
                        raise ValueError('Verified KAT input changed: ' + name)
                    pairs.append((source, name))
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


def recover_synthesis(source_run, run, inputs, config):
    """Reuse an intact prior synthesis without changing its evidence directory."""
    source_run = source_run.resolve()
    source_manifest = source_run / 'manifest.json'
    prior = json.loads(source_manifest.read_text())
    # The earlier scripts remain individually hash-verified. Only these driver
    # scripts may differ for the recovery/report-order change; design inputs,
    # constraints, firmware, provenance and implementation settings must match.
    script_names = {'implement_system.py', 'implement_system.tcl'}
    if set(prior['inputs']) != set(inputs):
        raise ValueError('Recovery input set differs from prior synthesis')
    for name, info in prior['inputs'].items():
        if sha(source_run / 'snapshot' / name) != info['sha256']:
            raise ValueError('Prior frozen implementation input changed: ' + name)
        if name not in script_names and info['sha256'] != inputs[name]['sha256']:
            raise ValueError('Recovery input differs from prior synthesis: ' + name)
    for name, expected in config.items():
        if prior.get(name) != expected:
            raise ValueError('Recovery configuration differs: ' + name)
    # Where available, the original archived result binds the manifest to the
    # completed tool invocation; it is not rewritten or promoted to success.
    previous_result = source_run / 'result.json'
    if not previous_result.is_file():
        raise ValueError('Recovery requires a finished prior invocation/result')
    previous = json.loads(previous_result.read_text())
    if previous.get('manifest_sha256') != sha(source_manifest):
        raise ValueError('Prior result does not authenticate its manifest')
    checkpoint = source_run / 'synth.dcp'
    with zipfile.ZipFile(checkpoint) as archive:
        if archive.testzip() is not None:
            raise ValueError('Prior synthesis checkpoint has a corrupt ZIP member')
        metadata_xml = ET.fromstring(archive.read('dcp.xml'))
        expected_metadata = dict(
            Top='mlkem1024_keccak_system' if config['variant'] == 'keccak' else 'cpu_benchmark_system',
            Part=config['part'], OutOfContext='1', BUILD_NUMBER='5239630',
            PRODUCT='Vivado v2024.2 (64-bit)')
        checkpoint_metadata = {}
        for name, expected in expected_metadata.items():
            elements = metadata_xml.findall(name)
            if len(elements) != 1 or elements[0].get('Name') != expected:
                raise ValueError('Recovered checkpoint XML metadata mismatch: ' + name)
            checkpoint_metadata[name] = elements[0].get('Name')
    checkpoint_hash = sha(checkpoint)
    shutil.copy2(checkpoint, run / 'synth.dcp')
    if sha(run / 'synth.dcp') != checkpoint_hash:
        raise ValueError('Copied synthesis checkpoint hash mismatch')
    return dict(kind='resume_synth', source_run=str(source_run),
        source_manifest_sha256=sha(source_manifest), source_result_sha256=sha(previous_result),
        source_exit_code=previous.get('exit_code'), checkpoint_sha256=checkpoint_hash,
        checkpoint_metadata=checkpoint_metadata,
        checkpoint_hash_recorded_utc=datetime.now(timezone.utc).isoformat(),
        hash_note='Checkpoint hash recorded at recovery selection, not before the original run',
        changed_scripts={name: dict(prior_sha256=prior['inputs'][name]['sha256'],
                                   recovery_sha256=inputs[name]['sha256'])
                         for name in sorted(script_names)})


def run_one(args, variant, group):
    tool_guard()
    run = args.run_root / group / variant
    run.mkdir(parents=True, exist_ok=False)
    inputs = prepare(variant, run, args.keccak_source)
    config = dict(variant=variant, part='xc7z020clg400-1', period_ns=10.0,
                  ram_bytes=131072, cpu='rv32im_fast', max_threads=8,
                  keccak_source=args.keccak_source)
    recovery = (recover_synthesis(args.resume_synth, run, inputs, config)
                if args.resume_synth else None)
    cmd = [str(args.vivado), '-mode', 'batch', '-source', str(run / 'snapshot/implement_system.tcl'),
           '-tclargs', str(run), variant]
    if recovery:
        cmd.append('resume_synth')
    manifest = dict(variant=variant, run_dir=str(run), started_utc=datetime.now(timezone.utc).isoformat(),
        inputs=inputs, command=cmd, part='xc7z020clg400-1', period_ns=10.0, ram_bytes=131072,
        cpu='rv32im_fast', max_threads=8, keccak_source=args.keccak_source,
        scope='Complete system OOC; assumed 2ns synchronous IO budget; not board implementation')
    if recovery:
        manifest['recovery'] = recovery
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
        result['checkpoint_sha256'] = {name: sha(run / name) for name in ('synth.dcp', 'routed.dcp')
                                       if (run / name).is_file()}
        if recovery and result['checkpoint_sha256'].get('synth.dcp') != recovery['checkpoint_sha256']:
            raise ValueError('Recovered synthesis checkpoint changed')
        result['timing_met'] = result['metrics']['timing_met']
        if process.returncode:
            raise ValueError('Vivado exit=' + str(process.returncode) + '; inspect retained reports')
        if set(result['checkpoint_sha256']) != {'synth.dcp', 'routed.dcp'}:
            raise ValueError('Implementation checkpoint missing; reports alone are not completion')
        result['implementation_completed'] = True
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
    parser.add_argument('--keccak-source', choices=('verified', 'current'), default='verified',
                        help='Use the frozen KAT RTL or current RTL candidate for the Keccak system')
    parser.add_argument('--variants', nargs='+', choices=('keccak', 'cpu_only'),
                        default=('keccak', 'cpu_only'),
                        help='Implementation targets; default runs the fair pair')
    parser.add_argument('--resume-synth', type=Path,
                        help='Prior variant run directory: validate/copy synth.dcp into a new run and skip synthesis')
    args = parser.parse_args()
    if args.resume_synth and len(args.variants) != 1:
        parser.error('--resume-synth requires exactly one --variants target')
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
        for variant in args.variants:
            results[variant] = run_one(args, variant, group)
        dump(RESULTS / group / 'comparison.json', results)
        dump(ROOT / 'build/keccak_cpu/implementation_progress.json', dict(status='finished', group=group,
             results=str(RESULTS / group / 'comparison.json')))
        print('SYSTEM_IMPL_FINISHED ' + str(RESULTS / group / 'comparison.json'), flush=True)
        # Report archiving succeeding does not imply the requested implementation
        # passed. Propagate tool/timing failures to the central flow and shell.
        return 0 if all(result.get('implementation_completed') and
                        result.get('timing_met') and result.get('exit_code') == 0
                        for result in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
