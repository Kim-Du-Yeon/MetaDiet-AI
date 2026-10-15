import importlib.util
from pathlib import Path
import sys


def load_harness():
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    sys.path.insert(0,str(scripts))
    spec=importlib.util.spec_from_file_location('feedback_soak',scripts/'check_feedback_soak.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fault_requires_bounded_failure_rollback_and_single_recovery():
    module=load_harness()
    good={'status':503,'unchanged':True,'recovery_status':200,'audit_once':True,'audit_unchanged':True}
    assert module.fault_passed(good)
    for key,value in [('status',500),('unchanged',False),('recovery_status',503),('audit_once',False),('audit_unchanged',False)]:
        assert not module.fault_passed({**good,key:value})
    assert not module.fault_passed({})


async def test_cancelled_account_creation_is_remembered_for_cleanup():
    import asyncio
    module=load_harness()
    track_creation=module.track_creation
    started=asyncio.Event();release=asyncio.Event();remembered=[]
    async def create():
        started.set()
        await release.wait()
        return {'id':'temporary-created-user'}
    task=asyncio.create_task(track_creation(create(),remembered.append))
    await started.wait()
    task.cancel()
    release.set()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert remembered==[{'id':'temporary-created-user'}]


def test_unknown_create_response_reconciles_only_exact_fixture_email():
    module=load_harness()
    pages={1:[{'id':str(i),'email':str(i)+'@real.invalid'} for i in range(100)],
           2:[{'id':'created-but-response-lost','email':'fixture@example.invalid'}]}
    assert module.reconcile_accounts(['fixture@example.invalid'],{},pages.get)==['created-but-response-lost']
    assert module.reconcile_accounts(['not-created@example.invalid'],{},lambda page:[])==[]
