"""A stand-in for the Anthropic client, so tests never call the real API."""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock


class FakeClaude:
    def __init__(self, answer=None, stop_reason='end_turn', raises=None, raw_text=None):
        self.text = raw_text if raw_text is not None else json.dumps(answer)
        self.stop_reason = stop_reason
        self.raises = raises
        self.requests = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._beta_stream))
        self.used_beta = False

    def with_options(self, **options):
        self.options = options
        return self

    def _beta_stream(self, **request):
        self.used_beta = True
        return self._stream(**request)

    @contextmanager
    def _stream(self, **request):
        self.requests.append(request)
        if self.raises:
            raise self.raises
        content = [] if self.stop_reason == 'refusal' else [SimpleNamespace(type='text', text=self.text)]
        message = SimpleNamespace(stop_reason=self.stop_reason, content=content)
        yield SimpleNamespace(get_final_message=lambda: message)

    def payload(self):
        """The JSON document the agent sent as the user message of its last request."""
        return json.loads(self.requests[-1]['messages'][0]['content'])


def use(fake):
    return mock.patch('core.agents.client.get_client', return_value=fake)
