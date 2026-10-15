export const feedbackStatuses = {received:'접수', reproducing:'재현 중', fixed:'수정 완료', resolved:'재검증 완료', on_hold:'보류'};
export const feedbackCategories = {general:'전반적인 의견', answer_quality:'답변 품질', evidence:'근거와 출처', usability:'사용 편의성', bug:'오류 신고'};
export const feedbackDate = value => new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'});
