"""

Sample bot executes your Python code.

modal deploy --name matplotlib main.py

python3 echobot.py
(assumes you already have modal set up)
"""

import re
from typing import AsyncIterable

import modal
from fastapi_poe import PoeBot, run
from fastapi_poe.client import MetaMessage, stream_request
from fastapi_poe.types import QueryRequest
from modal import Stub
from sse_starlette.sse import ServerSentEvent

# https://modalbetatesters.slack.com/archives/C031Z7H15DG/p1675177408741889?thread_ts=1675174647.477169&cid=C031Z7H15DG
modal.app._is_container_app = False

stub = Stub("run-python-code")


def redact_image_links(text):
    pattern = r"!\[.*\]\(http.*\)"
    redacted_text = re.sub(pattern, '', text)
    return redacted_text


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


def extract_code(reply):
    pattern = r"```python([\s\S]*?)```"
    matches = re.findall(pattern, reply)
    return "\n\n".join(matches)


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        print("user_statement")
        print(query.query[-1].content)

        for statement in query.query:
            statement.content = redact_image_links(statement.content)

        current_message = ""
        async for msg in stream_request(query, "matplotlibTool", query.api_key):
            # Note: See https://poe.com/CheckPythonTool for the prompt
            if isinstance(msg, MetaMessage):
                continue
            elif msg.is_suggested_reply:
                yield self.suggested_reply_event(msg.text)
            elif msg.is_replace_response:
                yield self.replace_response_event(msg.text)
            else:
                current_message += msg.text
                yield self.replace_response_event(current_message)

        code = extract_code(current_message)

        if not code:
            return

        print("code")
        print(code)

        if not code:
            return

        image_url = None
        try:
            f = modal.Function.lookup(
                "run-python-code-shared", "execute_code_matplotlib"
            )
            captured_output, image_data = f.call(code)  # need async await?
            if image_data:
                f = modal.Function.lookup("image-upload-shared", "upload_image")
                image_url = f.call(image_data)

        except modal.exception.TimeoutError:
            yield self.text_event("Time limit exceeded.")
            return
        if len(captured_output) > 5000:
            yield self.text_event(
                "\n\nThere is too much output, this is the partial output.\n\n"
            )
            captured_output = captured_output[:5000]
        reply_string = format_output(captured_output)

        if reply_string:
            yield self.text_event(reply_string)
        if image_url:
            print("image_url")
            print(image_url)
            yield self.text_event(f"\n\n![image]({image_url})")

        if not reply_string and not image_url:
            yield self.text_event("\n\nNo output or error recorded.")
            return


if __name__ == "__main__":
    run(EchoBot())
