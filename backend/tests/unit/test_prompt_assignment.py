import pytest
from app.core.prompt_assignment import ExperimentPolicy, choose_snapshot
from app.core.prompt_release_control import local_snapshot

def policy(**kwargs):
    return ExperimentPolicy("synthetic-exp",b"a"*32,(local_snapshot(),local_snapshot()),enabled=True,approved=True,**kwargs)

def test_synthetic1000_consistency_distribution_and_experiment_isolation():
    p=policy();labels=[p.group(f"owner-{i}","chat") for i in range(1000)]
    assert 450<=labels.count("B")<=550
    assert all(p.group(f"owner-{i}","chat")==p.group(f"owner-{i}","other") for i in range(1000))
    other=ExperimentPolicy("other-exp",b"a"*32,p.variants,enabled=True,approved=True)
    assert any(p.group(f"owner-{i}","chat")!=other.group(f"owner-{i}","chat") for i in range(100))

def test_disabled_and_pending_pin_rollback():
    p=policy();production=local_snapshot();assigned=p.assign("owner","chat")
    disabled=ExperimentPolicy(p.experiment_id,p.salt,p.variants,enabled=False,approved=False)
    assert choose_snapshot(production,assigned.wire,pending=True,policy=disabled,user="owner",thread="chat").digest==assigned.digest
    assert choose_snapshot(production,assigned.wire,pending=False,policy=disabled,user="owner",thread="chat").wire.get("experiment") is None
    assert choose_snapshot(production,assigned.wire,pending=False,policy=p,user="owner",thread="chat").serialized==assigned.serialized

def test_live_enable_alone_is_not_approval():
    p=ExperimentPolicy("synthetic-exp",b"a"*32,(local_snapshot(),local_snapshot()),enabled=True,approved=False)
    assert p.assign("owner","chat") is None

def test_same_experiment_id_cannot_silently_change_allocation_policy():
    p=policy();saved=p.assign('owner','thread')
    changed=ExperimentPolicy(p.experiment_id,p.salt,p.variants,enabled=True,approved=True,percent_b=10)
    with pytest.raises(ValueError):choose_snapshot(local_snapshot(),saved.wire,pending=False,policy=changed,user='owner',thread='thread')

def test_conversation_allocation_is_stable_but_can_differ_between_threads():
    p=policy(unit='conversation')
    assert p.group('owner','same')==p.group('owner','same')
    assert len({p.group('owner',str(i)) for i in range(100)})==2
