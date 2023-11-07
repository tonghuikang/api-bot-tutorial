"""

BOT_NAME="dalle3-mirror"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

Test message:
ChatGPT

"""
from __future__ import annotations

import json
import os
import time
import re
from typing import AsyncIterable

import fastapi_poe.client
from fastapi_poe import PoeBot, make_app
from fastapi_poe.client import stream_request
from fastapi_poe.types import (
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import Dict, Image, Stub, asgi_app
from openai import BadRequestError, OpenAI
from sse_starlette.sse import ServerSentEvent

fastapi_poe.client.MAX_EVENT_COUNT = 10000

DAY_IN_SECS = 24 * 60 * 60

# for non-subscribers, the message limit is defined in the bot settings
SUBSCRIBER_DAILY_MESSAGE_LIMIT = 10


stub = Stub("poe-bot-quickstart")
stub.my_dict = Dict.new()



def extract_prompt(reply):
    pattern = r"```prompt([\s\S]*?)```"
    matches = re.findall(pattern, reply)
    return ("\n\n".join(matches)).strip()



def prettify_time_string(second) -> str:
    second = int(second)
    hour, second = divmod(second, 60 * 60)
    minute, second = divmod(second, 60)

    string = "You can send the next message in"
    if hour == 1:
        string += f" {hour} hour"
    elif hour > 1:
        string += f" {hour} hours"

    if minute == 1:
        string += f" {minute} minute"
    elif minute > 1:
        string += f" {minute} minutes"

    if second == 1:
        string += f" {second} second"
    elif second > 1:
        string += f" {second} seconds"

    return string


user_allowlist = {"u-000000xy92lqvf0s6x4s2mn6so7bu4ye"}

USER_FOLLOWUP_PROMPT = """
Read my conversation.

Please write a description of the image that I intend to generate.

Put the description inside ```prompt
"""


class EchoBot(PoeBot):
    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[ServerSentEvent]:
        print(request.user_id)
        print(request.query[-1].content)

        client = OpenAI()

        dict_key = f"dalle3-mirror-limit-{request.user_id}"

        current_time = time.time()

        if dict_key not in stub.my_dict:
            stub.my_dict[dict_key] = []

        # thread safe?
        calls = stub.my_dict[dict_key]

        while calls and calls[0] <= current_time - DAY_IN_SECS:
            del calls[0]

        if (
            len(calls) >= SUBSCRIBER_DAILY_MESSAGE_LIMIT
            and request.user_id not in user_allowlist
        ):
            print(request.user_id, len(calls))
            time_remaining = calls[0] + DAY_IN_SECS - current_time
            yield PartialResponse(text=prettify_time_string(time_remaining))
            return

        calls.append(current_time)
        stub.my_dict[dict_key] = calls

        if len(request.query) > 2:
            # this is a multi-turn conversation
            print("len(request)", len(request.query))
            message = ProtocolMessage(role="user", content=USER_FOLLOWUP_PROMPT)
            request.query.append(message)

            inferred_reply = ""
            async for msg in stream_request(request, "ChatGPT", request.api_key):
                inferred_reply += msg.text

            instruction = extract_prompt(inferred_reply)

            if not instruction:
                yield PartialResponse(text=inferred_reply)
                return

            yield PartialResponse(text=f"```instruction\n{instruction}\n```\n\n")
        else:
            instruction = request.query[-1].content

        print(instruction)
        print(stub.my_dict[dict_key])

        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=instruction,
                size="1024x1024",
                quality="standard",
                n=1,
            )
        except BadRequestError as error:
            error_message = json.loads(error.response.content.decode())["error"][
                "message"
            ]
            yield PartialResponse(text=error_message)
            calls = stub.my_dict[dict_key]
            calls.remove(current_time)
            stub.my_dict[dict_key] = calls
            return

        revised_prompt = response.data[0].revised_prompt
        image_url = response.data[0].url

        print(image_url)

        yield PartialResponse(text=f"```prompt\n{revised_prompt}\n```\n\n")
        yield PartialResponse(text=f"![image]({image_url})")

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={"ChatGPT": 2},
            allow_attachments=False,  # to update when ready
            introduction_message="What do you want to generate with DALL·E 3?",
        )


bot = EchoBot()

image = (
    Image.debian_slim()
    .pip_install("fastapi-poe==0.0.23", "openai==1.1.0")
    .env(
        {
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
            "POE_ACCESS_KEY": os.environ["POE_ACCESS_KEY"],
        }
    )
)


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, api_key=os.environ["POE_ACCESS_KEY"])
    return app
