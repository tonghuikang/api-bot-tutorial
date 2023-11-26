"""

BOT_NAME="GPT4-128k-mirror"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

Test message:
ChatGPT

"""
from __future__ import annotations

import os
import random
import time
from typing import AsyncIterable

import fastapi_poe.client
import tiktoken
from fastapi_poe import PoeBot, make_app
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import Dict, Image, Stub, asgi_app
from openai import OpenAI
from sse_starlette.sse import ServerSentEvent

fastapi_poe.client.MAX_EVENT_COUNT = 10000

DAY_IN_SECS = 24 * 60 * 60

# for non-subscribers, the message limit is defined in the bot settings
SUBSCRIBER_DAILY_TOKEN_LIMIT = 200_000

encoding = tiktoken.encoding_for_model("gpt-4-1106-preview")


stub = Stub("poe-bot-quickstart")
stub.my_dict = Dict.new()

user_allowlist = {}


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


class EchoBot(PoeBot):
    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[ServerSentEvent]:
        print(request.user_id)
        print(request.query[-1].content)

        token_count = sum(
            len(encoding.encode(query.content)) for query in request.query
        )

        # randval = random.randint(0, int(token_count**0.5))
        # print("randval", randval)
        # if request.query[-1].content.startswith("[{'role': '") and randval > 0:
        #     yield PartialResponse(text="")
        #     time.sleep(random.randint(0, max(10, min(100, token_count))))
        #     return

        # check message limit
        dict_key = f"gpt4-mirror-token-limit-{request.user_id}"

        current_time = time.time()

        if dict_key not in stub.my_dict:
            stub.my_dict[dict_key] = []

        calls = stub.my_dict[dict_key]

        while calls and calls[0][0] <= current_time - DAY_IN_SECS:
            del calls[0]

        if len(calls) == 0 and token_count >= 1000:
            print(request.user_id, len(calls), token_count)
            yield PartialResponse(
                text="Please subscribe to Poe to send longer messages.\n\nIf you have subscribed, please start a new chat, send a short message, and then retry."
            )
            return

        if (
            sum(weight for _, weight in calls) >= SUBSCRIBER_DAILY_TOKEN_LIMIT
            and request.user_id not in user_allowlist
        ):
            print(request.user_id, len(calls))
            time_remaining = calls[0][0] + DAY_IN_SECS - current_time
            yield PartialResponse(text=prettify_time_string(time_remaining))
            return

        calls.append((current_time, token_count))
        stub.my_dict[dict_key] = calls
        print(calls)

        client = OpenAI()

        openai_messages = []
        for query in request.query:
            if query.role == "bot":
                openai_messages.append({"role": "assistant", "content": query.content})
            if query.role == "user":
                openai_messages.append({"role": query.role, "content": query.content})
            if query.role == "system":
                openai_messages.append({"role": query.role, "content": query.content})

        response = client.chat.completions.create(
            model="gpt-4-1106-preview", messages=openai_messages, stream=True
        )

        for chunk in response:
            if chunk.choices[0].finish_reason:
                return
            yield PartialResponse(text=chunk.choices[0].delta.content)

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={"GPT-4": 1},
            allow_attachments=False,
            introduction_message="",
        )


bot = EchoBot()

image = (
    Image.debian_slim()
    .pip_install("fastapi-poe==0.0.23", "openai==1.1.0", "tiktoken")
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
