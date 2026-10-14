"""Conservative eligibility for read-only follow-up coaching, not general intent routing."""
import re


def followup_needs_tools(message):
    """Only whole, ordinary advice requests can omit tools; unknown text keeps them."""
    foods = (r'(?:일반식|(?:한식)?뷔페|샌드위치|밥(?:\s*(?:이랑|랑|과|하고)\s*계란)?|'
             r'닭가슴살(?:\s*(?:이랑|랑|과|하고)\s*샐러드)?|계란|샐러드)')
    question = (r'\s*(?:(?:그럼|그러면|아침에|점심에|저녁에)\s*)?'
                r'(?:(?:한식)?뷔페\s*가서\s*)?(?:(?:편의점에서|일반식으로)\s*)?' + foods +
                r'(?:\s*한\s*접시)?\s*(?:먹어도\s*(?:괜찮아|괜찮을까|괜찮나요|돼|될까)|'
                r'먹는\s*건\s*(?:괜찮아|그런가))[.!?\s]*')
    # Optional display-format request for verified current values, not arbitrary instructions.
    header = (r'(?:첫\s*문장에\s*["“]오늘\s*섭취:\s*N\s*kcal,\s*하루\s*기준:\s*N\s*kcal["”]'
              r'\s*형식으로\s*적어줘[.!?\s]*)?')
    return re.fullmatch(question + header, message or '', re.I) is None


def simple_recommendation(state):
    """Allow only a complete, unambiguous advice request; never strip unknown text."""
    if (state.get('requested_action') or state.get('pending_proposal')
            or state.get('awaiting_confirmation')):
        return False
    return bool(re.fullmatch(
        r'\s*(?:오늘\s*)?(?:아침|점심|저녁)\s*(?:(?:메뉴|식단)(?:을)?\s*)?'
        r'추천(?:\s*해\s*줘|\s*해주세요)?[.!?\s]*'
        r'(?:(?:계획\s*카드는\s*만들지\s*말고\s*)?조언만\s*해\s*줘[.!?\s]*)?'
        r'(?:오늘\s*남은\s*칼로리도\s*알려\s*줘[.!?\s]*)?'
        r'(?:오늘 확정된 섭취량과 목표를 반영해줘\.[\s]*)?',
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
