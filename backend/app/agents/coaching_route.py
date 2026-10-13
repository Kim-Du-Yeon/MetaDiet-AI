"""Conservative eligibility for read-only follow-up coaching, not general intent routing."""
import re


def simple_recommendation(state):
    """Allow only a complete, unambiguous advice request; never strip unknown text."""
    if (state.get('requested_action') or state.get('pending_proposal')
            or state.get('awaiting_confirmation')):
        return False
    return bool(re.fullmatch(
        r'\s*(?:오늘\s*)?(?:아침|점심|저녁)\s*(?:(?:메뉴|식단)(?:을)?\s*)?'
        r'추천(?:\s*해\s*줘|\s*해주세요)?[.!?\s]*'
        r'(?:(?:계획\s*카드는\s*만들지\s*말고\s*)?조언만\s*해\s*줘[.!?\s]*)?'
        r'(?:오늘\s*남은\s*칼로리도\s*알려\s*줘[.!?\s]*)?',
        state.get('message', '')))


def simple_followup(state):
    if (state.get('requested_action') or state.get('pending_proposal')
            or state.get('awaiting_confirmation')):
        return False
    message = state.get('message', '')
    if len(message) > 160 or re.search(
        r'기록|저장|수정|삭제|취소|확정|계획|짜\s*줘|추가|남겨|바꿔|바꾸|빼\s*줘|넣어|등록|먹었|먹음|섭취했|목표|인바디|어제|내일|지난|당뇨|질환|임신|약|알레르기|증상|규칙|무시|지시', message):
        return False
    history = state.get('messages', [])[-6:]
    contents = [m.get('content', '') if isinstance(m, dict) else getattr(m, 'content', '') for m in history]
    if not any(isinstance(c, str) and re.search(r'(점심|저녁|아침|식단|메뉴).*(추천|조언)', c) for c in contents):
        return False
    return bool(re.search(r'뷔페|일반식|샌드위치|밥|계란|닭가슴살|샐러드', message)
                and re.search(r'먹어도|괜찮|그런가', message))
