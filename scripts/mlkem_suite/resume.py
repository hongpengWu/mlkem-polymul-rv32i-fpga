"""Sequential, restartable CPU-only KAT batches for ML-KEM-768/1024."""
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import json
import msvcrt
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/kat'))
from package_mlkem import load_cases, pack_fixture, verify_roundtrip
from collect import validate_log


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def local_cases(cases, indices):
    result = [copy.deepcopy(cases[i]) for i in indices]
    for index, case in enumerate(result):
        case['case_index'] = index
    return result


def validate_batch(batch, level, config, cases):
    meta = json.loads((batch / 'batch.json').read_text())
    assert meta['parameter_set'] == level and meta['config'] == config
    selected = local_cases(cases, meta['original_indices'])
    assert len(selected) == meta['case_count']
    for expected, suffix in ((False, 'input'), (True, 'expected')):
        words = pack_fixture(selected, level, expected)
        path = batch / f'mlkem{level}_{suffix}.mem'
        assert path.read_text() == ''.join(f'{word:08x}\n' for word in words), path
        verify_roundtrip(path, selected, level, expected)
    record = json.loads((batch / 'run_inputs.json').read_text())
    assert record['parameter_set'] == level and record['config'] == config
    assert record['ram_bytes'] == 131072 and record['stack_bytes'] == 32768
    for name, wanted in record['input_sha256'].items():
        if sha(ROOT / name) != wanted:
            raise RuntimeError(f'Frozen batch input changed: {name}')
    if (batch / 'success.json').exists():
        success = json.loads((batch / 'success.json').read_text())
        assert success['status'] == 'passed' and success['case_count'] == len(selected)
        assert success['log_sha256'] == sha(batch / 'simulate.log'), 'Saved log changed'
        assert success['run_inputs_sha256'] == sha(batch / 'run_inputs.json'), 'Saved inputs changed'
    return validate_log(batch / 'simulate.log', selected, config, 131072, 32768)


def prepare(level, config, cases, size):
    base = ROOT / f'results/official_baseline/mlkem{level}/batches/{config}'
    existing = sorted(base.glob('batch_*/batch.json'))
    if existing:
        indices = []
        for path in existing:
            m = json.loads(path.read_text())
            assert m['parameter_set'] == level and m['config'] == config
            assert m['case_count'] == len(m['original_indices'])
            indices.extend(m['original_indices'])
        assert len(indices) == len(set(indices)), 'Overlapping saved batch plan'
        if indices == list(range(len(cases))):
            return [path.parent for path in existing]
        # A shutdown during first preparation may leave a partial plan. Finish
        # only missing batches of the same partition, without touching evidence.
        expected_names = {f'batch_{start:03d}_{min(start+size,len(cases))-1:03d}'
                          for start in range(0, len(cases), size)}
        assert all(p.parent.name in expected_names for p in existing), 'Resume with original batch size'
    jobs = []
    for start in range(0, len(cases), size):
        indices = list(range(start, min(start + size, len(cases))))
        batch = base / f'batch_{start:03d}_{indices[-1]:03d}'
        if (batch / 'batch.json').exists():
            assert json.loads((batch / 'batch.json').read_text())['original_indices'] == indices
            jobs.append(batch)
            continue
        batch.mkdir(parents=True, exist_ok=True)
        selected = local_cases(cases, indices)
        for expected, suffix in ((False, 'input'), (True, 'expected')):
            path = batch / f'mlkem{level}_{suffix}.mem'
            words = pack_fixture(selected, level, expected)
            path.write_text(''.join(f'{word:08x}\n' for word in words), encoding='ascii', newline='\n')
            verify_roundtrip(path, selected, level, expected)
        write_json(batch / 'batch.json', dict(parameter_set=level, config=config,
                   original_indices=indices, case_count=len(indices)))
        jobs.append(batch)
    return jobs


def active_simulators():
    query = "@(Get-Process vivado,xsim,xsimk,xelab,xvlog -ErrorAction SilentlyContinue).Count"
    result = subprocess.check_output(['powershell', '-NoProfile', '-Command', query], text=True)
    return int(result.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parameter-set', type=int, required=True, choices=(768, 1024))
    p.add_argument('--config', choices=('rv32i', 'rv32im_iterative', 'rv32im_fast'), default='rv32im_fast')
    p.add_argument('--batch-size', type=int, default=8)
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--max-batches', type=int)
    p.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    args = p.parse_args()
    if not 1 <= args.batch_size <= 145 or (args.max_batches is not None and args.max_batches < 1):
        p.error('Invalid batch size/count')
    level, config = args.parameter_set, args.config
    build = ROOT / 'build/mlkem_suite'
    build.mkdir(parents=True, exist_ok=True)
    # Windows releases this kernel lock if the scheduler crashes or the PC shuts down.
    with (build / 'scheduler.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another generic KAT scheduler is active') from exc
        if active_simulators():
            raise RuntimeError('Vivado/XSim is active; do not launch or rewrite batches')
        cases, _ = load_cases(ROOT, level)
        # Preserve a completed full run; never start duplicate batches for it.
        full = ROOT / f'results/official_baseline/mlkem{level}/{config}/simulate.log'
        if full.exists():
            validate_log(full, cases, config, 131072, 32768)
            print(f'ALREADY_COMPLETE level={level} config={config}', flush=True)
            return
        jobs = prepare(level, config, cases, args.batch_size)
        pending = []
        for batch in jobs:
            if (batch / 'success.json').exists() or (batch / 'simulate.log').exists():
                validate_batch(batch, level, config, cases)
                print(f'SKIP_PASS {batch.name}', flush=True)
            else:
                pending.append(batch)
        print(f'RESUME level={level} passed={len(jobs)-len(pending)} pending={len(pending)}', flush=True)
        if args.prepare_only:
            return
        assert args.vivado.is_file(), f'Missing Vivado: {args.vivado}'
        if args.max_batches is not None:
            pending = pending[:args.max_batches]
        isa = 'rv32i' if config == 'rv32i' else 'rv32im'
        manifest_path = ROOT / f'results/official_baseline/mlkem{level}/build_manifest.json'
        manifest = next(b for b in json.loads(manifest_path.read_text()) if b['isa'] == isa)
        assert manifest['ram_bytes'] == 131072 and manifest['stack_reserved'] == 32768
        assert sha(ROOT / manifest['firmware']) == manifest['firmware_sha256']
        names = ['rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
                 'tb/software/tb_mlkem_suite.sv', 'scripts/mlkem_suite/run_batch.tcl',
                 'scripts/mlkem_suite/sim.tcl', 'scripts/mlkem_suite/resume.py',
                 'scripts/mlkem_suite/collect.py', 'scripts/kat/package_mlkem.py',
                 'scripts/kat/validate_acvp_json.py', 'firmware/mlkem_suite/kat_suite.c',
                 'firmware/mlkem_suite/mlkem_config.h', manifest['firmware'],
                 manifest_path.relative_to(ROOT).as_posix(),
                 f'tb/software/mlkem{level}_suite/cases.json']
        frozen = {name: sha(ROOT / name) for name in names}
        for name, wanted in manifest.get('source_sha256', {}).items():
            assert sha(ROOT / name) == wanted, f'Build source changed: {name}'
            frozen[name] = wanted
        for batch in pending:
            if (build / 'STOP').exists():
                print('STOPPED_BETWEEN_BATCHES', flush=True)
                return
            if active_simulators():
                raise RuntimeError('Another Vivado/XSim is active; checkpoint preserved')
            for name, wanted in frozen.items():
                assert sha(ROOT / name) == wanted, f'Input changed: {name}'
            meta = json.loads((batch / 'batch.json').read_text())
            attempt = uuid.uuid4().hex[:8]
            project = build / str(level) / config / batch.name / attempt
            project.mkdir(parents=True)
            hashes = dict(frozen)
            for name in ('batch.json', f'mlkem{level}_input.mem', f'mlkem{level}_expected.mem'):
                path = batch / name
                hashes[path.relative_to(ROOT).as_posix()] = sha(path)
            command = [str(args.vivado), '-mode', 'batch', '-source', str(ROOT / 'scripts/mlkem_suite/run_batch.tcl'),
                       '-log', str(project / 'vivado.log'), '-journal', str(project / 'vivado.jou'),
                       '-tclargs', str(level), config, str(batch), str(project), str(meta['case_count'])]
            # Failed console logs stay in separate attempt files. No active directory is removed.
            write_json(batch / 'run_inputs.json', dict(parameter_set=level, config=config,
                       simulator='Vivado/XSim 2024.2', ram_bytes=131072, stack_bytes=32768,
                       command=command, input_sha256=hashes,
                       started_at=datetime.datetime.now().astimezone().isoformat()))
            print(f'START {level}/{batch.name} cases={meta["case_count"]}', flush=True)
            with (batch / f'console_{attempt}.txt').open('w', encoding='utf-8') as output:
                code = subprocess.run(command, cwd=project, stdout=output, stderr=subprocess.STDOUT).returncode
            if code:
                raise RuntimeError(f'Vivado exit={code}: {batch}/console_{attempt}.txt')
            rows = validate_batch(batch, level, config, cases)
            write_json(batch / 'success.json', dict(status='passed', case_count=len(rows),
                       log_sha256=sha(batch / 'simulate.log'), run_inputs_sha256=sha(batch / 'run_inputs.json'),
                       finished_at=datetime.datetime.now().astimezone().isoformat()))
            print(f'PASS {level}/{batch.name} cases={len(rows)}', flush=True)
        print('SELECTED_BATCHES_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
