"""Validate, partition and run the RV32IM-fast profile, resuming passed batches."""
from pathlib import Path
import argparse
import concurrent.futures
import copy
import datetime
import json
import subprocess
import sys

from build import ROOT, BUILD, RESULTS, sha, require, save
sys.path.insert(0, str(ROOT / 'scripts/kat'))
from package_mlkem512 import pack_fixture, verify_roundtrip


def prepare(cases):
    dirs = []
    for first in range(0,145,8):
        indices = list(range(first,min(first+8,145)))
        directory = RESULTS / 'batches' / f'batch_{first:03d}_{indices[-1]:03d}'
        dirs.append(directory)
        if (directory/'batch.json').exists():
            require(json.loads((directory/'batch.json').read_text(encoding='utf-8'))['original_indices']==indices,
                    f'Changed batch partition: {directory}')
            continue
        directory.mkdir(parents=True,exist_ok=True)
        selected = [copy.deepcopy(cases[i]) for i in indices]
        for i,c in enumerate(selected): c['case_index']=i
        sizes = {}
        for expected,name,key in [(False,'mlkem512_input.mem','input_words'),(True,'mlkem512_expected.mem','expected_words')]:
            words=pack_fixture(selected,expected)
            path=directory/name
            path.write_text(''.join(f'{w:08x}\n' for w in words),encoding='ascii',newline='\n')
            verify_roundtrip(path,selected,expected)
            sizes[key]=len(words)
        sizes.update({direction+'_bytes':sum(len(c[direction][f])//2 for c in selected for f in c[direction+'_fields'])
                      for direction in ['input','output']})
        save(directory/'batch.json',dict(schema_version=1,config='rv32im_fast',case_count=len(indices),original_indices=indices,**sizes))
    return dirs


def run_batch(directory, vivado, manifest, cases):
    from collect import validate_batch
    metadata=json.loads((directory/'batch.json').read_text(encoding='utf-8'))
    project=BUILD/'batches'/directory.name
    project.mkdir(parents=True,exist_ok=True)
    names=set(manifest['source_sha256']) | set(manifest['baseline_paths_sha256'])
    names.update(['scripts/mlkem512_profile/run.py','scripts/mlkem512_profile/run.tcl',
                  'scripts/mlkem512_suite/sim.tcl','tb/software/tb_mlkem512_profile.sv',
                  'results/official_baseline/mlkem512/profile/build_manifest.json',manifest['firmware']])
    names.update((directory/n).relative_to(ROOT).as_posix() for n in ['batch.json','mlkem512_input.mem','mlkem512_expected.mem'])
    inputs={n:sha(ROOT/n) for n in sorted(names)}
    command=[str(vivado),'-mode','batch','-source',str(ROOT/'scripts/mlkem512_profile/run.tcl'),
             '-log',str(project/'vivado.log'),'-journal',str(project/'vivado.jou'),
             '-tclargs',str(directory),str(project),str(metadata['case_count'])]
    save(directory/'run_inputs.json',dict(input_sha256=inputs,command=command,config='rv32im_fast',
          simulator='Vivado/XSim 2024.2',ram_bytes=65536,started_at=datetime.datetime.now().astimezone().isoformat()))
    print(f'PROFILE_START {directory.name} cases={metadata["case_count"]}',flush=True)
    with (directory/'console.txt').open('w',encoding='utf-8') as output:
        code=subprocess.run(command,cwd=project,stdout=output,stderr=subprocess.STDOUT).returncode
    require(code==0,f'Vivado failed ({code}): {directory/"console.txt"}')
    for name,digest in inputs.items(): require(sha(ROOT/name)==digest,f'Run input changed: {name}')
    staging=project/'mlkem512.sim/sim_1/behav/xsim'
    staged={name:sha(staging/name) for name in ['mlkem512.mem','mlkem512_input.mem','mlkem512_expected.mem','simulate.log']}
    require(staged['mlkem512.mem']==manifest['firmware_sha256'],'Staged firmware mismatch')
    for name in ['mlkem512_input.mem','mlkem512_expected.mem','simulate.log']:
        require(staged[name]==sha(directory/name),f'Staged content mismatch: {name}')
    save(directory/'staged_hashes.json',staged)
    success=directory/'success.json'
    save(success,dict(status='passed',case_count=metadata['case_count'],log_sha256=sha(directory/'simulate.log'),
         run_inputs_sha256=sha(directory/'run_inputs.json'),batch_sha256=sha(directory/'batch.json'),
         project_sha256=sha(directory/'project.xpr'),staged_hashes_sha256=sha(directory/'staged_hashes.json'),
         finished_at=datetime.datetime.now().astimezone().isoformat()))
    try: validate_batch(directory,manifest,cases)
    except Exception:
        success.unlink(missing_ok=True)
        raise
    print(f'PROFILE_PASS {directory.name} cases={metadata["case_count"]}',flush=True)


def main():
    from collect import validate_batch
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vivado',type=Path,default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--max-batches',type=int)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    require(1<=args.workers<=6,'Choose 1..6 workers')
    manifest=json.loads((RESULTS/'build_manifest.json').read_text(encoding='utf-8'))
    for mapping in ['source_sha256','baseline_paths_sha256']:
        for name,digest in manifest[mapping].items(): require(sha(ROOT/name)==digest,f'Changed build input: {name}')
    require(sha(ROOT/manifest['firmware'])==manifest['firmware_sha256'],'Changed profile image')
    cases=json.loads((ROOT/'tb/software/mlkem512_suite/cases.json').read_text(encoding='utf-8'))['cases']
    jobs=prepare(cases); pending=[]
    for directory in jobs:
        if (directory/'success.json').exists(): validate_batch(directory,manifest,cases)
        else: pending.append(directory)
    print(f'PROFILE_RESUME passed_batches={len(jobs)-len(pending)} pending_batches={len(pending)}',flush=True)
    if args.prepare_only:return
    if args.max_batches is not None:
        require(args.max_batches>0,'Positive batch limit required')
        pending=pending[:args.max_batches]
    stop=BUILD/'STOP'
    iterator=iter(pending)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active={}
        def submit_one():
            if stop.exists():return
            directory=next(iterator,None)
            if directory is not None:active[pool.submit(run_batch,directory,args.vivado,manifest,cases)]=directory
        for _ in range(args.workers):submit_one()
        while active:
            done,_=concurrent.futures.wait(active,return_when=concurrent.futures.FIRST_COMPLETED)
            for task in done:
                active.pop(task)
                task.result()
            for _ in done:submit_one()
    print('PROFILE_STOPPED' if stop.exists() else 'PROFILE_SELECTED_COMPLETE',flush=True)


if __name__=='__main__':main()
