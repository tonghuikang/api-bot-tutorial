"""

Sample bot executes your Python code.

python3 echobot.py
(assumes you already have modal set up)
"""

from typing import AsyncIterable

import modal
from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest
from modal import Stub
from sse_starlette.sse import ServerSentEvent

# https://modalbetatesters.slack.com/archives/C031Z7H15DG/p1675177408741889?thread_ts=1675174647.477169&cid=C031Z7H15DG
modal.app._is_container_app = False

stub = Stub("run-python-code")


def format_output(captured_output, captured_error="") -> str:
    lines = []

    if captured_output:
        line = f"\n```output\n{captured_output}\n```"
        lines.append(line)

    if captured_error:
        line = f"\n```error\n{captured_error}\n```"
        lines.append(line)

    return "\n".join(lines)


def strip_code(code):
    if len(code.strip()) < 6:
        return code
    code = code.strip()
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3]
    return code


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        print("user_statement", query.query[-1].content)
        code = query.query[-1].content
        code = strip_code(code)
        with stub.run():
            try:
                f = modal.Function.lookup("run-python-code-shared", "execute_code")
                captured_output = f.call(code)  # need async await?
            except modal.exception.TimeoutError:
                yield self.text_event("Time limit exceeded.")
                return
        if len(captured_output) > 5000:
            yield self.text_event(
                "There is too much output, this is the partial output."
            )
            captured_output = captured_output[:5000]
        reply_string = format_output(captured_output)
        if not reply_string:
            yield self.text_event("No output or error recorded.")
            return
        yield self.text_event(reply_string)


if __name__ == "__main__":
    run(EchoBot())
