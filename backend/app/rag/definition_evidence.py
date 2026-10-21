"""Conservative definition-request gate; semantic support is assessed by the controller."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.agentic import Assessment

_DEFINITION_REQUEST = re.compile(
    r'^\s*(?:please\s+)?define\b|\bhow\s+(?:does|do|is|are)\b.+?\b(?:define|defined)\b|'
    r'\b(?:definition|meaning)\s+of\b|\bwhat\s+does\b.+?\bmean\b|'
    r'(?:정의|의미|뜻)(?:는|은|이|가|을|를|란)?\s*(?:뭐|무엇|알려|설명|궁금)|'
    r'(?:무슨|어떤)\s*(?:의미|뜻)|이란\s*(?:무엇|뭐)', re.IGNORECASE)


def apply_definition_gate(question: str, decision: Assessment) -> tuple[Assessment, bool]:
    requested = bool(_DEFINITION_REQUEST.search(question)) or decision.definition_support in {
        'direct', 'related_only', 'missing'}
    if not requested or (decision.definition_support == 'direct' and decision.supported_excerpts):
        return decision, False
    missing = list(decision.missing_core)
    marker = 'Direct definition of the concept requested in the original question'
    if marker not in missing and len(missing) < 4:
        missing.append(marker)
    # Preserve the original subject; never replace it with a related concept.
    rewrite = (' '.join(question.split())[:800] +
        ' Direct definition, meaning or defining relation of the requested concept; not a related concept.')
    return decision.model_copy(update={
        'sufficient': False, 'missing_core': missing, 'rewrite': rewrite,
        'supported_excerpts': [],
    }), True
