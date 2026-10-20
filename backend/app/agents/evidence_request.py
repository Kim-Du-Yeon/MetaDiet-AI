"""Recognize source-seeking language without forcing retrieval for plain advice."""
import re


def requests_document_evidence(message: str) -> bool:
    text = re.sub(r'\s+', '', message or '')
    # A request to summarize one's own records is not an external-evidence request.
    text = re.sub(r'(?:내|오늘|확정된|섭취|식사)*(?:기록|목표)(?:에|을)?(?:근거해서|근거로|기반으로)', '', text)
    return bool(re.search(
        r'영양학적|근거해(?:서)?|근거로|근거기반|출처|논문|공식(?:영양)?지침|'
        r'(?:자료|문서|지침|연구|영양근거).*(?:찾|검색|참고|기반|설명|알려)|'
        r'(?:찾|검색).*(?:자료|문서|지침|연구)|(?:과학적|영양성분지식)', text))
