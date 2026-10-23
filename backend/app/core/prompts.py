"""Packaged, versioned primary templates. No user data, remote fetch or secrets."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

from app.core.config import get_settings

RELEASE_ROOT = Path(__file__).resolve().parents[1]/'prompts'/'releases'


@lru_cache(maxsize=4)
def load_release(release):
    if not re.fullmatch(r'v[1-9][0-9]*',release or ''):
        raise ValueError('Invalid prompt release')
    path=RELEASE_ROOT/(release+'.json')
    if not path.is_file(): raise ValueError('Unknown prompt release')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('release')!=release or not isinstance(data.get('prompts'),dict):
        raise ValueError('Invalid prompt release manifest')
    entries={}
    for name,entry in data['prompts'].items():
        if (not isinstance(entry,dict) or not isinstance(entry.get('text'),str) or
            not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',entry.get('version',''))):
            raise ValueError('Invalid prompt version')
        if hashlib.sha256(entry['text'].encode()).hexdigest()!=entry.get('sha256'):
            raise ValueError('Prompt hash mismatch')
        entries[name]=MappingProxyType(dict(entry))
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return MappingProxyType(entries),digest


def prompt_metadata(name=None,*,release=None):
    from app.core.prompt_release_control import current_snapshot
    snapshot=current_snapshot() if release is None else None
    if snapshot is not None:
        result=snapshot.metadata()
        if name is not None:
            entry=snapshot.wire['manifest']['prompts'][name]
            result.update(prompt_id=name,prompt_version=entry['version'],prompt_sha256=entry['sha256'])
        return result
    release=release or getattr(get_settings(),'prompt_release','v1')
    entries,digest=load_release(release)
    result={'prompt_release':release,'prompt_bundle_sha256':digest,
            'prompt_scope':'registered_primary_templates'}
    if name is not None:
        if name not in entries: raise ValueError('Unknown prompt ID')
        result.update(prompt_id=name,prompt_version=entries[name]['version'],prompt_sha256=entries[name]['sha256'])
    return result


def get_prompt(name,*,release=None):
    from app.core.prompt_release_control import current_snapshot
    snapshot=current_snapshot() if release is None else None
    if snapshot is not None:return snapshot.text(name)
    release=release or getattr(get_settings(),'prompt_release','v1')
    entries,_=load_release(release)
    if name not in entries: raise ValueError('Unknown prompt ID')
    return entries[name]['text']


class RegisteredChatPrompt:
    """Construct the small template from the request-pinned registry at use time."""
    def __init__(self,name,human):self.name=name;self.human=human
    def format_messages(self,**kwargs):
        from langchain_core.prompts import ChatPromptTemplate
        return ChatPromptTemplate.from_messages([("system",get_prompt(self.name)),("human",self.human)]).format_messages(**kwargs)
