"""Disposable public authorization probe. No real feedback is changed.

prepare -> administrator reviews the marked fixture in the browser -> probe -> cleanup.
Credentials stay in a git-ignored env file; outputs contain no opinions or tokens.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib import request, error
from uuid import uuid4
from check_render_beta import load_env, service_api, json_request, ROOT

API = 'https://metadiet-api.onrender.com'
ENV = ROOT / 'backend/.env.admin-feedback-check'
ARTIFACT = ROOT / 'backend/artifacts/admin-feedback-public.json'


def prepare():
    if ENV.exists():
        raise RuntimeError('fixture_exists_use_cleanup_first')
    marker = uuid4().hex
    email, password = f'feedback-check-{marker}@example.invalid', f'T!{uuid4().hex}a9'
    user = service_api('/auth/v1/admin/users', 'POST', {'email':email,'password':password,'email_confirm':True})
    # Persist the identity immediately so a subsequent failed request is recoverable.
    ENV.write_text('ADMIN_FEEDBACK_AUTH_ID='+user['id']+'\n', encoding='utf-8')
    token = service_api('/auth/v1/token?grant_type=password', 'POST', {'email':email,'password':password})['access_token']
    with ENV.open('a',encoding='utf-8') as output:
        output.write('ADMIN_FEEDBACK_TOKEN='+token+'\n')
    result = json_request(API+'/users/onboarding',token=token,method='POST',payload={
        'goal':'diet','region':'KR','height_cm':175,'weight_kg':82,'age':35,'sex':'male',
        'activity':'low_active','general_adult_confirmed':True,'target_weight_kg':75,
        'target_date':'2027-04-30','goal_priority':'balance'})
    proposal = result['pending_proposal']
    json_request(API+'/proposals/decision',token=token,method='POST',payload={
        'proposal_id':proposal['id'],'version':proposal['version'],'action':'cancel'})
    feedback = json_request(API+'/feedback',token=token,method='POST',payload={
        'rating':5,'category':'bug','comment':'ADMIN FEEDBACK BROWSER CHECK '+marker[:8]+' - synthetic UI review only',
        'client_submission_id':str(uuid4())})
    with ENV.open('a',encoding='utf-8') as output:
        output.write('ADMIN_FEEDBACK_ID='+feedback['id']+'\n')
    print(json.dumps({'fixture_prepared':True,'marker':marker[:8]}))


def status(path, token=None, method='GET', payload=None):
    req = request.Request(API+path,method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    try:
        with request.urlopen(req,timeout=45) as response:
            return response.status
    except error.HTTPError as exc:
        return exc.code


def probe():
    import os
    token, feedback_id = os.environ['ADMIN_FEEDBACK_TOKEN'], os.environ['ADMIN_FEEDBACK_ID']
    checks={}
    for name,path,method,payload in [
        ('list','/admin/feedback','GET',None),
        ('detail','/admin/feedback/'+feedback_id,'GET',None),
        ('update','/admin/feedback/'+feedback_id,'PATCH',{'version':1,'status':'resolved','admin_note':'unauthorized'}),
    ]:
        checks['anonymous_'+name]=status(path,method=method,payload=payload)
        checks['member_'+name]=status(path,token=token,method=method,payload=payload)
        assert checks['anonymous_'+name]==401
        assert checks['member_'+name]==403
    row=service_api('/rest/v1/beta_feedback?id=eq.'+feedback_id+'&select=status,version,admin_note')[0]
    assert row['status']=='resolved' and row['version']>=2 and row['admin_note']=='Browser verification completed'
    result={'scope':'synthetic_public_functional_not_performance','authorization_http_statuses':checks,
            'browser_saved_state_persisted':True,'unauthorized_update_no_change':True,
            'build':json_request(API+'/health')['build']['commit']}
    ARTIFACT.parent.mkdir(parents=True,exist_ok=True)
    ARTIFACT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


def cleanup():
    import os
    token = os.environ.get('ADMIN_FEEDBACK_TOKEN')
    auth_id = os.environ['ADMIN_FEEDBACK_AUTH_ID']
    if token:
        json_request(API+'/users/me',token=token,method='DELETE',payload={'confirmation':'DELETE'})
    else:
        service_api('/auth/v1/admin/users/'+auth_id,'DELETE')
    if ARTIFACT.exists():
        result=json.loads(ARTIFACT.read_text())
        result['synthetic_fixture_cleanup']='deleted'
        ARTIFACT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    ENV.unlink()
    print(json.dumps({'synthetic_fixture_cleanup':'deleted'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['prepare','probe','cleanup']); args=parser.parse_args()
    load_env(ROOT/'backend/.env')
    if ENV.exists():load_env(ENV)
    try:
        {'prepare':prepare,'probe':probe,'cleanup':cleanup}[args.mode]()
    except Exception as exc:
        # Deliberately omit exception bodies: auth failures may contain sensitive server details.
        print(json.dumps({'stage':args.mode,'error_type':type(exc).__name__,'fixture_retained_for_cleanup':ENV.exists()}))
        sys.exit(1)
