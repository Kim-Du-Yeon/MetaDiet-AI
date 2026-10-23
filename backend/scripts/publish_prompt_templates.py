"""Publish static templates privately; does not sign, promote, or start user A/B."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
from dotenv import load_dotenv
from app.core.prompt_release_control import CONTRACTS,OUTPUTS,REPOS,_snapshot
from app.core.langsmith_prompts import make_client,LangSmithReleaseReader

def main(output):
    load_dotenv(ROOT/"backend/.env",override=True)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    private=ROOT/"backend/.env.prompt-signer"
    public=ROOT/"backend/app/prompts/approval-public-key.json"
    if not private.exists():
        key=Ed25519PrivateKey.generate()
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        public.write_text(json.dumps({"algorithm":"Ed25519","public_key":base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()},indent=2),encoding="utf-8")
    from langchain_core.prompts import ChatPromptTemplate
    client=make_client();reader=LangSmithReleaseReader(client)
    original=json.loads((ROOT/"backend/app/prompts/releases/v1.json").read_text(encoding="utf-8"))
    candidate=json.loads(json.dumps(original));candidate["release"]="v2"
    entry=candidate["prompts"]["team.compact_followup"]
    entry["version"]="1.1.0"
    entry["text"]+="\n확정 섭취 기록·현재 하루 목표·아직 먹지 않은 예정 식사를 구분하세요. 약속이나 계획은 확정 섭취량에 합산하지 마세요.\n단백질·지방이 충분하다는 수치 판단은 해당 영양소의 현재 확정량과 같은 단위의 현재 목표가 모두 있을 때만 하세요. 비교 근거가 없으면 충분하다고 단정하지 마세요.\n확인된 현재 수치와 실천 가능한 일반식 조언은 제공하되,예정 식사를 이유로 굶거나 고정 칼로리를 보상하도록 처방하지 마세요."
    entry["sha256"]=hashlib.sha256(entry["text"].encode()).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    (output/"candidate-v2.json").write_text(json.dumps(candidate,ensure_ascii=False,indent=2),encoding="utf-8")
    saved_path=output/"release-drafts.json"
    saved=json.loads(saved_path.read_text(encoding="utf-8")) if saved_path.exists() else {}
    for release in [original,candidate]:
        name=release["release"];existing=saved.get(name,{"kind":"evaluation","manifest":{"schema_version":1,"release":name,"prompts":{}},"texts":{},"origin_commit":None})
        for prompt,entry in release["prompts"].items():
            if prompt in existing["texts"] and existing["texts"][prompt]==entry["text"]:continue
            if name=="v2" and entry["text"]==original["prompts"][prompt]["text"]:
                reference=saved["v1"]["manifest"]["prompts"][prompt]
            else:
                repo=REPOS[prompt];record=client.get_prompt(repo)
                if record is not None and record.is_public is not False:raise ValueError("Refuse public prompt")
                template=ChatPromptTemplate.from_messages([("system",entry["text"])])
                from langsmith.utils import LangSmithConflictError
                try:
                    client.push_prompt(repo,object=template,is_public=False,commit_tags=["metadiet-"+name],
                        commit_description="Static MetaDiet registered template; no user data")
                except LangSmithConflictError:
                    previous, _ = reader.pull(repo,"latest",allow_latest=True)
                    if previous != entry["text"]: raise
                text,commit=reader.pull(repo,"latest",allow_latest=True)
                if text!=entry["text"]:raise ValueError("Remote template readback mismatch")
                reference={"repo":repo,"commit":commit,"sha256":entry["sha256"],"version":entry["version"],"input_variables":list(CONTRACTS[prompt]),"output_contract":OUTPUTS[prompt]}
            existing["manifest"]["prompts"][prompt]=reference;existing["texts"][prompt]=entry["text"]
            saved[name]=existing;saved_path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding="utf-8")
        _snapshot(existing)
    print(json.dumps({"private_template_count":8,"frozen_drafts":list(saved),"promoted":False,"runtime_ab_enabled":False}))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();main(a.output)
