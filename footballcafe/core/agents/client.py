"""The one place the site talks to Claude. Both agents ask for JSON and get a dict back."""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

# If a safety classifier declines a request, the API retries it on the model
# Anthropic recommends for that kind of decline instead of failing outright.
FALLBACK_BETA = 'server-side-fallback-2026-07-01'


class AgentError(Exception):
    """Claude could not give a usable answer. The caller decides what happens next."""


class AgentRefused(AgentError):
    """Claude declined to handle the content."""


def takes_effort_and_fallbacks(model: str) -> bool:
    """Haiku 4.5, the cheap model the cafe runs on by default, rejects the `effort` option and has no
    refusal fallback. The bigger models (Sonnet, Opus) take both, so they get them when one is configured."""
    return not model.startswith('claude-haiku')


def get_client():
    return anthropic.Anthropic()


def ask_json(*, model, system, payload, schema, effort, max_tokens, timeout):
    """Send `payload` (JSON-serialisable) to Claude and return its answer parsed against `schema`.

    The payload goes in as a JSON document, so reader-written text inside it
    stays a quoted string and cannot pose as part of the instructions.
    """
    client = get_client().with_options(timeout=timeout, max_retries=1)
    request = {
        'model': model,
        'max_tokens': max_tokens,
        'system': system,
        'output_config': {'format': {'type': 'json_schema', 'schema': schema}},
        'messages': [{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
    }
    if takes_effort_and_fallbacks(model):
        request['output_config']['effort'] = effort
        request.update(betas=[FALLBACK_BETA], fallbacks='default')
        open_stream = client.beta.messages.stream
    else:
        open_stream = client.messages.stream
    try:
        with open_stream(**request) as stream:
            message = stream.get_final_message()
    except TypeError as error:
        # The SDK raises TypeError when no API key or login is configured.
        raise AgentError('Claude is not set up: add ANTHROPIC_API_KEY to .env.') from error
    except anthropic.AuthenticationError as error:
        raise AgentError('Claude rejected the API key.') from error
    except anthropic.RateLimitError as error:
        raise AgentError('Claude is rate-limiting us. Try again in a minute.') from error
    except anthropic.APIStatusError as error:
        logger.warning('Claude API error %s (request %s)', error.status_code, error.request_id)
        raise AgentError(f'Claude returned an error ({error.status_code}).') from error
    except anthropic.APIConnectionError as error:
        raise AgentError('Could not reach Claude.') from error

    if message.stop_reason == 'refusal':
        raise AgentRefused('Claude declined to handle this content.')
    if message.stop_reason == 'max_tokens':
        raise AgentError("Claude's answer was cut off.")
    text = next((block.text for block in message.content if block.type == 'text'), '')
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as error:
        raise AgentError("Claude's answer was not valid JSON.") from error
    if not isinstance(answer, dict):
        raise AgentError("Claude's answer had the wrong shape.")
    return answer
