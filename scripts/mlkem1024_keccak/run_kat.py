"""Frozen, sequential full-KEM hardware KAT. Default: three representative cases.

--remaining resumes missing cases only; successful cases are validated and never
rerun. A STOP file in build/keccak_cpu stops scheduling after the current batch.
No recurring automation is created. Failed attempts are retained.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'results/keccak_cpu/kat'
BUILD = ROOT / 'build/keccak_cpu'
sys.path.insert(0, str(ROOT / 'scripts/kat'))
from package_mlkem import load_cases, pack_fixture, verify_roundtrip


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def tool_guard():
    cmd = ('Get-Process vivado,xsim,xsimk,xelab,xvlog,vitis_hls -ErrorAction SilentlyContinue | '
           'Select-Object -ExpandProperty Id')
    found = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True)
    if found.stdout.strip():
        raise RuntimeError('Active FPGA tools; refusing duplicate launch. PIDs=' + found.stdout.strip())


def verify_snapshot(run, manifest):
    for name, info in manifest['inputs'].items():
        p = (run / 'snapshot' / name).resolve()
        if not p.is_relative_to((run / 'snapshot').resolve()) or not p.is_file() or sha(p) != info['sha256']:
            raise RuntimeError('Frozen input changed: ' + name)


def version_inputs(inputs):
    # Batch fixtures vary by selected cases. The scheduler Python is provenance,
    # not an elaboration input; changing its resume checks does not change RTL.
    excluded = {'run_kat.py', 'fixtures/mlkem1024_input.mem', 'fixtures/mlkem1024_expected.mem'}
    return {name: info['sha256'] for name, info in inputs.items() if name not in excluded}


def require_same_version(manifest, expected, evidence):
    actual = version_inputs(manifest['inputs'])
    changed = sorted(name for name in actual.keys() | expected.keys()
                     if actual.get(name) != expected.get(name))
    config = (manifest.get('parameter_set'), manifest.get('config'),
              manifest.get('ram_bytes'), manifest.get('stack_bytes'))
    if changed or config != (1024, 'rv32im_fast', 131072, 32768):
        raise RuntimeError('Different KAT input version at ' + str(evidence) +
                           '; use a new --results-dir and --build-dir. Changed: ' +
                           ', '.join(changed or ['system configuration']))


def completed_indices(cases, expected):
    from collect_kat import validate_log
    completed = set()
    for result_file in (EVIDENCE / 'batches').glob('*/*/result.json'):
        if not result_file.with_name('manifest.json').is_file():
            raise RuntimeError('Result has no input manifest: ' + str(result_file))
    # Check all attempts, including failed/interrupted ones, before skipping any
    # successful cases. A result root belongs to exactly one hardware version.
    for manifest_file in sorted((EVIDENCE / 'batches').glob('*/*/manifest.json')):
        manifest = json.loads(manifest_file.read_text())
        require_same_version(manifest, expected, manifest_file.parent)
        result_file = manifest_file.with_name('result.json')
        if not result_file.exists():
            continue
        result = json.loads(result_file.read_text())
        if not result.get('passed'):
            continue
        evidence = result_file.parent
        if sha(manifest_file) != result['input_manifest_sha256'] or sha(evidence / 'simulate.log') != result['output_sha256']['simulate.log']:
            raise RuntimeError('Changed success evidence: ' + str(evidence))
        verify_snapshot(Path(manifest['run_dir']), manifest)
        indices = manifest['original_indices']
        validate_log((evidence / 'simulate.log').read_text(), cases, indices)
        if completed.intersection(indices):
            raise RuntimeError('Duplicate successful case coverage')
        completed.update(indices)
    return completed


def current_input_pairs(args):
    build_file = EVIDENCE / 'build.json'
    # Candidate roots may reuse the verified firmware record without rebuilding
    # or modifying historical results. Existing records are never overwritten.
    if not build_file.exists():
        build_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.build_record, build_file)
    build = json.loads(build_file.read_text())
    for name, digest in build['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError('Stale firmware build: ' + name)
    if sha(ROOT / build['firmware']) != build['firmware_sha256']:
        raise RuntimeError('Firmware image changed')
    selection_file = ROOT / 'results/hls/mlkem1024_keccak/rtl_equivalence.json'
    selected = json.loads(selection_file.read_text())['selected']
    for name, info in selected.items():
        if sha(args.hls_run / 'p/sol1/syn/verilog' / name) != info['raw_sha256']:
            raise RuntimeError('HLS RTL differs from verified selection: ' + name)
    pairs = [(ROOT / name, Path('rtl') / Path(name).name) for name in
             ('rtl/cpu/picorv32.v', 'rtl/accelerator/keccak_mmio_adapter.sv',
              'rtl/accelerator/mlkem1024_keccak_system.sv')]
    pairs += [(ROOT / 'tb/accelerator/tb_mlkem1024_keccak_kat.sv', Path('tb/tb_mlkem1024_keccak_kat.sv')),
              (Path(__file__).with_suffix('.tcl'), Path('run_kat.tcl')),
              (Path(__file__), Path('run_kat.py')),
              (build_file, Path('build.json')), (selection_file, Path('hls_selection.json')),
              (ROOT / build['firmware'], Path('fixtures/mlkem1024.mem'))]
    pairs += [(ROOT / name, Path('source') / name) for name in build['source_sha256']]
    pairs += [(args.hls_run / 'p/sol1/syn/verilog' / name, Path('hls') / name) for name in selected]
    return pairs


def run_batch(args, cases, indices, pairs, expected):
    from collect_kat import validate_log
    tool_guard()
    for source, relative in pairs:
        if relative.as_posix() in expected and sha(source) != expected[relative.as_posix()]:
            raise RuntimeError('Input changed since scheduler start: ' + str(source))
    tag = 'pilot_000_001_115' if indices == [0, 1, 115] else f'batch_{indices[0]:03}_{indices[-1]:03}'
    run = args.run_root / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run.mkdir(parents=True, exist_ok=False)
    evidence = EVIDENCE / 'batches' / tag / run.name
    evidence.mkdir(parents=True, exist_ok=False)
    frozen = {}
    for source, relative in pairs:
        target = run / 'snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        frozen[relative.as_posix()] = dict(source=str(source), sha256=sha(target))
    if version_inputs(frozen) != expected:
        raise RuntimeError('Input changed while freezing snapshot; failed directory retained: ' + str(run))
    local_cases = deepcopy([cases[i] for i in indices])
    for local, case in enumerate(local_cases):
        case['case_index'] = local
    for is_expected, suffix in ((False, 'input'), (True, 'expected')):
        relative = f'fixtures/mlkem1024_{suffix}.mem'
        path = run / 'snapshot' / relative
        path.write_text(''.join(f'{w:08x}\n' for w in pack_fixture(local_cases, 1024, is_expected)), encoding='ascii')
        verify_roundtrip(path, local_cases, 1024, is_expected)
        frozen[relative] = dict(source='Generated from pinned public ACVP cases', sha256=sha(path))
    cmd = [str(args.vivado), '-mode', 'batch', '-source', str(run / 'snapshot/run_kat.tcl'),
           '-tclargs', str(run), str(len(indices)), str(args.threads)]
    manifest = dict(started_utc=datetime.now(timezone.utc).isoformat(), run_dir=str(run), command=cmd,
                    case_count=len(indices), original_indices=indices, inputs=frozen,
                    ram_bytes=131072, stack_bytes=32768, parameter_set=1024, config='rv32im_fast',
                    hls_run=str(args.hls_run), max_threads=args.threads,
                    scope='Full ML-KEM-1024 API on RV32IM-fast with hardware-only FIPS202')
    dump(run / 'manifest.json', manifest)
    shutil.copy2(run / 'manifest.json', evidence / 'manifest.json')
    dump(BUILD / 'kat_progress.json', dict(status='running', batch=tag, indices=indices,
         scheduler_pid=os.getpid(), run_dir=str(run), console=str(run / 'console.txt')))
    print(f'KECCAK_KAT_START {tag} indices={indices} run={run}', flush=True)
    started = time.monotonic()
    with (run / 'console.txt').open('w', encoding='utf-8') as log:
        process = subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    # Even Tcl/elaboration failures retain their logs and original snapshot.
    generated_log = run / 'p/keccakkat.sim/sim_1/behav/xsim/simulate.log'
    if not (run / 'simulate.log').exists() and generated_log.exists():
        shutil.copy2(generated_log, run / 'simulate.log')
    passed, error = False, ''
    try:
        if process.returncode:
            raise RuntimeError('Vivado exit=' + str(process.returncode))
        verify_snapshot(run, manifest)
        rows, hardware = validate_log((run / 'simulate.log').read_text(), cases, indices)
        passed = True
    except Exception as exc:
        error = str(exc)
    output_sha256 = {}
    for name in ('simulate.log', 'console.txt'):
        if (run / name).exists():
            shutil.copy2(run / name, evidence / name)
            output_sha256[name] = sha(evidence / name)
    result = dict(passed=passed, exit_code=process.returncode, elapsed_seconds=elapsed, error=error,
                  completed_utc=datetime.now(timezone.utc).isoformat(),
                  input_manifest_sha256=sha(run / 'manifest.json'), output_sha256=output_sha256)
    dump(run / 'result.json', result)
    dump(evidence / 'result.json', result)
    print(f'KECCAK_KAT_FINISHED {tag} passed={passed} seconds={elapsed:.1f} error={error}', flush=True)
    if not passed:
        dump(BUILD / 'kat_progress.json', dict(status='failed', run_dir=str(run), error=error))
        raise RuntimeError('Failed attempt retained: ' + str(run))


def main():
    global EVIDENCE, BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remaining', action='store_true')
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--hls-run', type=Path, default=Path('E:/hls/k4_io1/opt02'))
    parser.add_argument('--run-root', type=Path, default=Path('E:/hls/k4kat'))
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    parser.add_argument('--results-dir', type=Path, default=EVIDENCE,
                        help='Evidence root; use a new root for an RTL candidate')
    parser.add_argument('--build-dir', type=Path, default=BUILD,
                        help='Progress/lock root paired with --results-dir')
    parser.add_argument('--build-record', type=Path, default=EVIDENCE / 'build.json',
                        help='Verified firmware record to seed a new result root')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 8 or not 1 <= args.threads <= 8 or not args.vivado.is_file():
        raise ValueError('Invalid batch size, threads or Vivado path')
    EVIDENCE = args.results_dir.resolve()
    BUILD = args.build_dir.resolve()
    BUILD.mkdir(parents=True, exist_ok=True)
    with (BUILD / 'kat.lock').open('a+b') as guard:
        guard.seek(0)
        if not guard.read(1):
            guard.write(b'0'); guard.flush()
        guard.seek(0)
        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        cases, _ = load_cases(ROOT, 1024)
        pairs = current_input_pairs(args)
        expected = version_inputs({relative.as_posix(): {'sha256': sha(source)}
                                   for source, relative in pairs})
        completed = completed_indices(cases, expected)
        requested = list(range(len(cases))) if args.remaining else [0, 1, 115]
        pending = [i for i in requested if i not in completed]
        print(f'KECCAK_KAT_RESUME completed={len(completed)} pending={len(pending)}', flush=True)
        for offset in range(0, len(pending), args.batch_size):
            if (BUILD / 'STOP').exists():
                print('KECCAK_KAT_STOP checkpoint preserved', flush=True)
                return
            indices = pending[offset:offset + args.batch_size]
            run_batch(args, cases, indices, pairs, expected)
            completed.update(indices)
            dump(BUILD / 'kat_progress.json', dict(status='checkpoint', completed_indices=sorted(completed)))
        print(f'KECCAK_KAT_REQUEST_COMPLETE unique_cases={len(completed)}/145', flush=True)
        if completed == set(range(145)):
            # Final strict aggregation runs once, in this scheduler; no heartbeat.
            subprocess.run([sys.executable, str(Path(__file__).with_name('collect_kat.py')),
                            '--results-dir', str(EVIDENCE), '--write'], cwd=ROOT, check=True)
            dump(BUILD / 'kat_progress.json', dict(status='complete', completed_indices=sorted(completed)))


if __name__ == '__main__':
    main()
