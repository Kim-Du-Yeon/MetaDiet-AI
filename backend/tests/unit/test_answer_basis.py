from app.agents.answer_basis import build_answer_basis


def test_only_explicit_known_citations_are_attached():
    response, basis = build_answer_basis('説明 [근거:known] [근거:fake]',
        evidence={'known': {'source':'guide.pdf','page':'5','excerpt':'reviewed'},
                  'unused': {'source':'unused.pdf','page':'9'}}, search_attempted=True)
    assert response == '説明 [근거 1] '
    assert [doc['source'] for doc in basis['documents']] == ['guide.pdf']
    assert basis['limitation'] is None


def test_retrieved_does_not_mean_cited():
    _, basis = build_answer_basis('일반 안내', evidence={'a':{'source':'guide.pdf'}}, search_attempted=True)
    assert basis['documents'] == []
    assert '명시적 인용' in basis['limitation']


def test_record_snapshot_allowlists_fields_and_keeps_unknown_targets():
    _, basis = build_answer_basis('답변', profile={'strategy':{'protein_g':100}, 'secret':'no'},
        intake={'date':'2026-10-19','meals':[{'id':'private','food_name':'밥','quantity_g':200,
            'meal_type':'lunch','calories':300,'protein_g':5,'carbs_g':60,'fat_g':1}]})
    assert basis['records']['totals']['protein_g'] == 5
    assert basis['targets']['protein_g'] == 100
    assert basis['targets']['daily_calories'] is None
    assert 'private' not in str(basis)
    assert 'secret' not in str(basis)
    assert '수행하지' in basis['limitation']


def test_failed_search_is_not_missing_records():
    _, basis = build_answer_basis('답변', search_attempted=True)
    assert basis['records'] is None
    assert '확보하지' in basis['limitation']
