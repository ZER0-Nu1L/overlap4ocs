import copy
import tempfile
import unittest
from pathlib import Path

from config.cc_algorithm import compute_algorithm_params
from paradigm.baseline import compute_baseline_schedule
from paradigm.model_pulp import build_model, compute_bigM
from utils.fig11_validation import cct_metrics, model_residuals, replay, validate_schedule
from utils.solver_evidence import parse_cbc_log


def params(k=2, p=8, m=32, tr=.2):
    x = dict(k=k, p=p, m=m, B=25, T_reconf=tr, T_lat=.02, solver='pulp')
    x.update(compute_algorithm_params('ar_having-doubling', p, m))
    return x


class ValidationTests(unittest.TestCase):
    def test_baseline_and_legitimate_slack(self):
        p = params()
        cct, schedule = compute_baseline_schedule(p)
        self.assertTrue(validate_schedule(p, schedule, cct)['valid'])
        self.assertTrue(validate_schedule(p, schedule, cct+10)['valid'])
        ends = {i: max(x['t_end'] for x in schedule if x['step']==i) for i in p['m_i']}
        ends[p['num_steps']] += 1
        self.assertTrue(validate_schedule(p, schedule, cct+1, ends)['valid'])

    def test_reject_corrupt_data_integer_conflict_and_missing(self):
        p = params()
        cct, schedule = compute_baseline_schedule(p)
        for field, delta in (('d', 1), ('used', .25), ('t_reconf_start', -1)):
            bad = copy.deepcopy(schedule)
            bad[0][field] += delta
            self.assertFalse(validate_schedule(p, bad, cct)['valid'], field)
        self.assertFalse(validate_schedule(p, schedule[:-1], cct)['valid'])
        bad = copy.deepcopy(schedule)
        bad[-1]['t_reconf_start'] = bad[-1]['t_reconf_end'] = 0
        self.assertFalse(validate_schedule(p, bad, cct)['valid'])

    def test_initial_use_after_skipped_same_configuration(self):
        p = params()
        p.update(num_steps=2, m_i={1:1.,2:1.}, configurations={1:1,2:1})
        model, cct, d, ts, te, u, r, rs, re, ends = build_model(p)
        # Old r >= u - same_config admitted this unsafe assignment.
        u[1,2].varValue=0; u[2,2].varValue=1; r[2,2].varValue=0
        self.assertLess(model.constraints['r_def_step_2_2'].value(), 0)

    def test_time_big_m_covers_all_steps_and_latency(self):
        p=params(m=.001,tr=.0001)
        p.update(num_steps=100, m_i={i:.001 for i in range(1,101)})
        _, bound=compute_bigM(p)
        self.assertGreaterEqual(bound, sum(p['m_i'].values())/p['B']+100*(p['T_lat']+p['T_reconf']))

    def test_replay_single_plane_and_no_reconfiguration(self):
        p=params(k=1)
        cct,schedule=compute_baseline_schedule(p)
        a,_=replay(p,schedule); b,_=replay(p,schedule,True)
        self.assertAlmostEqual(a,b)
        self.assertAlmostEqual(a,cct)
        p=params(tr=0)
        cct,schedule=compute_baseline_schedule(p)
        self.assertAlmostEqual(replay(p,schedule)[0],replay(p,schedule,True)[0])

    def test_hand_computed_overlap(self):
        p=dict(k=2, num_steps=2, B=1., T_lat=0., T_reconf=2.,
               m_i={1:4.,2:4.}, configurations={1:1,2:2})
        decisions=[]
        for i in (1,2):
            for j in (1,2):
                used=int(j==i)
                decisions.append(dict(step=i,ocs=j,d=4.*used,used=used,reconf=used))
        a,sa=replay(p,decisions)
        b,sb=replay(p,decisions,True)
        self.assertEqual(a,10.)
        self.assertEqual(b,12.)
        self.assertEqual(sum(x['d'] for x in sa),sum(x['d'] for x in sb))

    def test_metrics_fields_are_independent(self):
        a=cct_metrics(10,8,5); b=cct_metrics(10,6,5)
        self.assertEqual(a['baseline_gap_pct'],b['baseline_gap_pct'])
        self.assertNotEqual(a['swot_gap_pct'],b['swot_gap_pct'])
        self.assertNotEqual(a['gain_pct'],b['gain_pct'])
        with self.assertRaises(ValueError):
            cct_metrics(0,1,1)

    def test_all_model_constraints_and_variable_bounds(self):
        p=params()
        model,*_=build_model(p)
        self.assertFalse(model_residuals(model)['valid'])


class GridTests(unittest.TestCase):
    def rows(self):
        import itertools
        from utils.fig11_data import ALGORITHMS, LATENCIES, SIZES
        return [dict(algorithm=a,T_reconf=t,message_mib=m,p=256,k=4,B=25,T_lat=.02,
                     solver='pulp',solver_time_limit=120,solver_gap=.05,solver_threads=8,
                     solver_seed=1,status='success',baseline_cct=10,optimized_cct=8,ideal_cct=5)
                for a,t,m in itertools.product(ALGORITHMS,LATENCIES,SIZES)]

    def test_exact_grid_and_reject_missing_duplicate_mixed_budget(self):
        from utils.fig11_data import validate_grid
        rows=self.rows()
        self.assertEqual(len(validate_grid(rows)),84)
        for bad in (rows[:-1], rows+[rows[0]], [dict(rows[0],solver_time_limit=600)]+rows[1:],
                    [dict(rows[0],status='failed')]+rows[1:]):
            with self.assertRaises(ValueError): validate_grid(bad)


class TerminationTests(unittest.TestCase):
    def test_termination_is_not_pulp_status(self):
        cases=[('Optimal solution found','optimal',True),
               ('Optimal solution found (within gap tolerance)','gap_tolerance',False),
               ('Stopped on time limit','time_limit',False),
               ('Problem proven infeasible','infeasible',False),
               ('Linear relaxation unbounded','unbounded',False)]
        for text,expected,proven in cases:
            r=parse_cbc_log('Result - '+text+'\n',10,1)
            self.assertEqual(r['termination'],expected)
            self.assertEqual(r['proven_optimal'],proven)
        self.assertFalse(parse_cbc_log('Result - Stopped on time limit\nNo feasible solution found\n',10,0)['has_incumbent'])
        self.assertEqual(parse_cbc_log('truncated',10,2)['termination'],'unknown')

    def test_bound_precision_recorded(self):
        r=parse_cbc_log('Result - Stopped on time limit\nLower bound: 1.234\nGap: 0.5\n',2,2)
        self.assertEqual(r['bound_reported_raw_ms'],1.234)
        self.assertAlmostEqual(r['bound_conservative_raw_ms'],1.2335)
        self.assertEqual(r['reported_cbc_gap'],.5)


if __name__ == '__main__':
    unittest.main()
