import hashlib
import json
import pickle
from pathlib import Path


def test_release_bundle_contains_activated_build_and_matching_corpus():
    root=Path(__file__).resolve().parents[3]
    folder=root/'backend/app/rag/release'
    manifest=json.loads((folder/'activation.json').read_text(encoding='utf-8'))
    data=(folder/'chunks.pkl').read_bytes()
    assert hashlib.sha256(data).hexdigest()==manifest['chunks_sha256']
    docs=pickle.loads(data)  # Trusted, committed build artifact only.
    assert len(docs)==manifest['chunk_count']==4139
    assert all(d.metadata['embedding_model']==manifest['embedding_model'] and
               d.metadata['embedding_dimension']==manifest['embedding_dimension'] for d in docs)
    assert 'COPY --chown=app:app backend/app/rag/release/ ./app/rag/' in (root/'backend/Dockerfile').read_text()
