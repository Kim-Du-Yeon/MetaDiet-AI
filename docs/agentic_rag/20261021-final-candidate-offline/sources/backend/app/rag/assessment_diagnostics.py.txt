"""Content-free controller diagnostics. Never serialize provider error messages."""
from collections.abc import Mapping
from enum import Enum
import json
import logging

FINISH_REASONS = frozenset({
    'STOP', 'MAX_TOKENS', 'SAFETY', 'RECITATION', 'OTHER', 'BLOCKLIST',
    'PROHIBITED_CONTENT', 'SPII', 'MALFORMED_FUNCTION_CALL', 'LANGUAGE',
    'FINISH_REASON_UNSPECIFIED', 'UNEXPECTED_TOOL_CALL', 'TOO_MANY_TOOL_CALLS',
})
PARSER_TYPES = frozenset({'ValidationError', 'OutputParserException', 'JSONDecodeError',
                          'ValueError', 'TypeError'})


class AssessmentOutputError(ValueError):
    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__('Invalid evidence assessment: ' + diagnostic['failure_reason'])


def diagnostic_for(payload, *, context_chars: int, prompt_version: str, prompt_sha256: str) -> dict:
    """Allowlisted metadata only; absent token counts stay null, never zero."""
    envelope = payload if isinstance(payload, Mapping) else {}
    raw = envelope.get('raw')
    metadata = getattr(raw, 'response_metadata', None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    finish = metadata.get('finish_reason')
    if isinstance(finish, Enum):
        finish = finish.name
    finish = finish if isinstance(finish, str) else None
    # LangChain versions may serialize the enum as FinishReason.MAX_TOKENS.
    if finish and finish.startswith('FinishReason.'):
        finish = finish.removeprefix('FinishReason.')
    normalized = finish if finish in FINISH_REASONS else 'MISSING' if not finish else 'UNRECOGNIZED'
    raw_usage = getattr(raw, 'usage_metadata', None)
    usage = raw_usage if isinstance(raw_usage, Mapping) else {}
    counts = {}
    invalid = raw_usage is not None and not isinstance(raw_usage, Mapping)
    for field in ('input_tokens', 'output_tokens', 'total_tokens'):
        value = usage.get(field)
        valid = type(value) is int and value >= 0
        counts[field] = value if valid else None
        invalid |= field in usage and not valid
    details = usage.get('output_token_details')
    details = details if isinstance(details, Mapping) else {}
    reasoning = details.get('reasoning')
    valid_reasoning = type(reasoning) is int and reasoning >= 0
    counts['reasoning_tokens'] = reasoning if valid_reasoning else None
    invalid |= 'reasoning' in details and not valid_reasoning
    present = sum(counts[field] is not None for field in ('input_tokens', 'output_tokens', 'total_tokens'))
    status = 'invalid' if invalid else 'complete' if present == 3 else 'partial' if present else 'missing'
    parsing_error = envelope.get('parsing_error')
    error_type = type(parsing_error).__name__ if parsing_error is not None else None
    return {'prompt_version': prompt_version, 'prompt_sha256': prompt_sha256,
            'context_chars': context_chars, 'output_token_limit': 512,
            'finish_reason': normalized, 'usage_status': status, 'usage': counts,
            'parsing_error_present': parsing_error is not None,
            'parsing_error_type': error_type if error_type in PARSER_TYPES else 'other' if error_type else None,
            'parsed_present': envelope.get('parsed') is not None,
            'failure_reason': None}


def log_diagnostic(diagnostic: dict) -> None:
    logging.getLogger(__name__).log(
        logging.WARNING if diagnostic['failure_reason'] else logging.INFO,
        'rag_assessment_diagnostic %s', json.dumps(diagnostic, sort_keys=True),
        extra={'assessment_diagnostic': diagnostic})
