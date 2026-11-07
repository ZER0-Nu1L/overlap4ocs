#!/usr/bin/env python3
"""Reproduce corrected Figure 11 and its numerical table without a solver."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils.fig11_data import ALGORITHMS, validate_grid
from utils.fig11_plot import plot_figure11


def reproduce(source, output):
    source, output = Path(source), Path(output)
    with source.open(newline='') as stream:
        rows = validate_grid(list(csv.DictReader(stream)))
    report = plot_figure11(rows, output)
    fields = ['algorithm', 'T_reconf', 'message_mib', 'baseline_cct',
              'optimized_cct', 'ideal_cct', 'swot_gap_pct', 'gain_pct']
    for name in ('termination', 'fallback', 'selected_cct_gap_upper'):
        if all(name in row for row in rows):
            fields.append(name)
    table = output.with_suffix('.csv')
    rows.sort(key=lambda r: (float(r['T_reconf']), ALGORITHMS.index(r['algorithm']),
                             float(r['message_mib'])))
    with table.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    report['input_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    report['output_sha256'] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [output.with_suffix('.pdf'), output.with_suffix('.png'), table]
    }
    report['message_unit'] = 'decimal MB (legacy column name: message_mib)'
    report['initial_preconfiguration_excluded'] = True
    output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS: {len(rows)} points; plot: {output.with_suffix(".pdf")}; table: {table}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'data/fig11-correction/results.csv')
    parser.add_argument('--output', type=Path,
                        default=ROOT/'figures/paper_reproduce/exp2.2_impact_Treconf.pdf')
    args = parser.parse_args()
    reproduce(args.input, args.output)


if __name__ == '__main__':
    main()
