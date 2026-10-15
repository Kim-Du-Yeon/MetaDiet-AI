"""Administrator-only feedback review; never trace or log opinion bodies."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from app.core.auth import get_current_admin
from app.db.admin_feedback import AdminFeedbackRepository, FeedbackStatus, InvalidAssignee
from app.db.feedback import FeedbackCategory, FeedbackStorageUnavailable


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/admin/feedback', dependencies=[Depends(no_store)])


class FeedbackReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(gt=0)
    status: FeedbackStatus
    admin_note: str = Field(default='', max_length=1000)
    assignee_id: UUID | None = None


@router.get('')
async def list_feedback(_admin: str = Depends(get_current_admin),
                        status: FeedbackStatus | None = None, category: FeedbackCategory | None = None,
                        limit: Annotated[int, Query(ge=1, le=100)] = 20,
                        offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    try:
        return await AdminFeedbackRepository().list(status=status, category=category, limit=limit, offset=offset)
    except FeedbackStorageUnavailable:
        raise HTTPException(503, '피드백 목록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.') from None


@router.get('/assignees')
async def list_assignees(_admin: str = Depends(get_current_admin)):
    try:
        return await AdminFeedbackRepository().assignees()
    except FeedbackStorageUnavailable:
        raise HTTPException(503, '담당자 목록을 불러오지 못했습니다.') from None


@router.get('/{feedback_id}/history')
async def feedback_history(feedback_id: UUID, _admin: str = Depends(get_current_admin),
                           limit: Annotated[int, Query(ge=1, le=100)] = 20,
                           before_version: Annotated[int | None, Query(gt=0)] = None):
    try:
        result = await AdminFeedbackRepository().history(feedback_id, limit=limit, before_version=before_version)
    except FeedbackStorageUnavailable:
        raise HTTPException(503, '변경 이력을 불러오지 못했습니다.') from None
    if result is None:
        raise HTTPException(404, '피드백이 없거나 삭제됐습니다.')
    return result


@router.get('/{feedback_id}')
async def get_feedback(feedback_id: UUID, _admin: str = Depends(get_current_admin)):
    try:
        row = await AdminFeedbackRepository().get(feedback_id)
    except FeedbackStorageUnavailable:
        raise HTTPException(503, '피드백을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.') from None
    if row is None:
        raise HTTPException(404, '피드백이 없거나 삭제됐습니다.')
    return row


@router.patch('/{feedback_id}')
async def review_feedback(feedback_id: UUID, body: FeedbackReview, admin: str = Depends(get_current_admin)):
    try:
        row = await AdminFeedbackRepository().update(feedback_id, version=body.version, status=body.status,
            admin_note=body.admin_note.strip(), admin_auth_id=admin,
            **({'assignee_id': body.assignee_id} if 'assignee_id' in body.model_fields_set else {}))
    except InvalidAssignee:
        raise HTTPException(422, '허용된 관리자만 담당자로 지정할 수 있습니다.') from None
    except FeedbackStorageUnavailable:
        raise HTTPException(503, '변경 내용을 저장하지 못했습니다. 입력을 유지하고 다시 시도해주세요.') from None
    if row is None:
        raise HTTPException(409, '다른 관리자가 변경했거나 삭제된 피드백입니다. 최신 내용을 다시 불러와주세요.')
    return row
