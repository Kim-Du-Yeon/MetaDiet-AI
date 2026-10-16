def test_kiwi_uses_one_worker_without_changing_model_or_dictionary(monkeypatch):
    from app.rag import retriever
    import kiwipiepy
    calls=[]
    monkeypatch.setattr(retriever,'_kiwi',None)
    monkeypatch.setattr(kiwipiepy,'Kiwi',lambda **kwargs: calls.append(kwargs) or object())
    one=retriever._get_kiwi()
    assert retriever._get_kiwi() is one
    assert calls==[{'num_workers':1}]
