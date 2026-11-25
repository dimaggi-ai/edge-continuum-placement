"""Public constructor and capacity boundaries, with finite corrected recovery."""
from dataclasses import asdict, replace
import unittest
from continuum.tiers import Tier, TOWER, HUB, METRO_POP, CENTRAL, LADDER, custom
from continuum.workloads import Workload, LIBRARY, workload
from continuum.place import evaluate, place


class InputValidationTests(unittest.TestCase):
    def test_real_fields_refuse_invalid_values(self):
        groups = [(TOWER, ('ai_power_kw','max_gpu_watts','km_to_user','km_to_parent','transit_rtt_ms')),
                  (LIBRARY[0], ('access_rtt_ms','ingest_gbps','gpu_watts','latency_sla_ms'))]
        for obj, fields in groups:
            for field in fields:
                invalid = [float('nan'), -float('inf'), -1, True, False, '1', None, 1j, 10**400]
                if field != 'latency_sla_ms':
                    invalid.append(float('inf'))
                if field == 'gpu_watts':
                    invalid.append(0)
                for value in invalid:
                    with self.subTest(field=field, value=repr(value)):
                        with self.assertRaisesRegex(ValueError, field):
                            replace(obj, **{field:value})

    def test_counts_flags_names_and_enums(self):
        for obj, field, minimum in [(TOWER,'max_fabric_gpus',0),(LIBRARY[0],'gpus',1)]:
            for value in (True, False, 1.5, '2', None, -1, float('inf'), float('nan'), 10**400, minimum-1):
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaisesRegex(ValueError, field): replace(obj, **{field:value})
        for obj, field in [(TOWER,'staffed'),(LIBRARY[0],'sovereign')]:
            for value in ('false',0,1,None):
                with self.assertRaisesRegex(ValueError, field): replace(obj, **{field:value})
        for obj in (TOWER,LIBRARY[0]):
            for value in ('','  ',None,1):
                with self.assertRaisesRegex(ValueError,'name'): replace(obj,name=value)
            self.assertEqual(replace(obj,name='custom site / workload').name,'custom site / workload')
        for obj,field in [(TOWER,'cooling'),(TOWER,'fabric'),(LIBRARY[0],'collective'),(LIBRARY[0],'data_gravity'),(LIBRARY[0],'resilience_class')]:
            for value in ('unknown',None,[],True):
                with self.assertRaisesRegex(ValueError,field): replace(obj,**{field:value})
        with self.assertRaisesRegex(ValueError,'note'): replace(LIBRARY[0],note=None)

    def test_zero_boundaries_and_batch_infinity(self):
        t=replace(TOWER,ai_power_kw=0,max_gpu_watts=0,max_fabric_gpus=0,km_to_user=0,km_to_parent=0,transit_rtt_ms=0)
        self.assertEqual(t.power_gpus(75),0)
        self.assertEqual(evaluate(LIBRARY[0],t).status,'BLOCKED')
        replace(LIBRARY[0],latency_sla_ms=0,access_rtt_ms=0,ingest_gbps=0)
        self.assertEqual(sum(w.latency_sla_ms==float('inf') for w in LIBRARY),3)
        self.assertEqual(place(workload('frontier-pretrain')).recommended,'central-factory')
        self.assertEqual(replace(LIBRARY[0],latency_sla_ms=float('inf')).latency_sla_ms,float('inf'))

    def test_nan_gate_bypass_refusal_and_corrected_recovery(self):
        for name,t,status in [('ran-l1-baseband',METRO_POP,'BLOCKED'),('ric-xapp-loop',CENTRAL,'BLOCKED'),('telemetry-anomaly',METRO_POP,'COSTLY'),('video-vlm',CENTRAL,'COSTLY')]:
            before=asdict(t)
            for make in (lambda: replace(t,km_to_user=float('nan')),lambda:custom(t.name,km_to_user=float('nan')),lambda:Tier(**dict(before,km_to_user=float('nan')))):
                with self.assertRaisesRegex(ValueError,'km_to_user'): make()
            self.assertEqual(asdict(t),before)
            self.assertEqual(evaluate(workload(name),custom(t.name,km_to_user=t.km_to_user)).status,status)
        with self.assertRaisesRegex(ValueError,'latency_sla_ms'):
            Workload(**dict(asdict(LIBRARY[0]),latency_sla_ms=float('nan')))

    def test_public_power_arguments_and_derived_range(self):
        for field in ('gpu_watts','overhead'):
            for value in (float('nan'),float('inf'),-float('inf'),0,-1,True,'1',None,1j,10**400):
                args={'gpu_watts':75,'overhead':1.35};args[field]=value
                with self.assertRaisesRegex(ValueError,field): TOWER.power_gpus(**args)
        for t,gpu,overhead in [(replace(TOWER,ai_power_kw=1e308),75,1.35),(replace(TOWER,ai_power_kw=10**308),75,1.35),(TOWER,1e308,1e308),(TOWER,1e-300,1e-300),(TOWER,5e-324,1)]:
            with self.assertRaisesRegex(ValueError,'power_gpus'): t.power_gpus(gpu,overhead)
        self.assertEqual(TOWER.power_gpus(75,0.5),40)
        self.assertEqual(TOWER.power_gpus(75),14)

if __name__ == '__main__': unittest.main()
