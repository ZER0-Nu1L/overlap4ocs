#!/usr/bin/env python3
"""Run the corrected Figure 11 matrix sequentially, with preserved run evidence."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, help='Smoke run only this many points')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    command = [sys.executable, '-u', 'scripts/matrix_runner.py', '--matrix',
               'config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml',
               '--main-script', 'scripts/fig11_run.py', '--skip-artifact-copy',
               '--fail-fast', '--resume', '--rerun-failed', '--heartbeat-sec', '30']
    if args.limit is not None:
        command.extend(['--limit', str(args.limit)])
    subprocess.run(command, cwd=ROOT, check=True)
    if args.limit is None:
        subprocess.run([sys.executable, 'scripts/reproduce_fig11.py', '--input',
                        'logs/matrix_results-exp2.2-matrix_sweep_msg+Tr.csv', '--output',
                        'figures/fig11_rerun/exp2.2_impact_Treconf.pdf'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
