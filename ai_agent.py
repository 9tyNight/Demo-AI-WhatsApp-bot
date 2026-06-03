import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

ODOO_API_BASE_URL = os.getenv("ODOO_API_BASE_URL", "http://127.0.0.1:8000")
USE_OPENAI = os.getenv("USE_OPENAI", "0") == "1"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

FRUSTRATION_WORDS = {
    "angry",
    "annoyed",
    "bad service",
    "complaint",
    "frustrated",
    "human",
    "manager",
    "operator",
    "person",
    "representative",
    "speak to someone",
    "terrible",
    "unhappy",
}


@dataclass
class AgentResult:
    reply: str
    human_handoff: bool
    tool_calls: list[dict[str, Any]]


def search_inventory(query: str, in_stock_only: bool = False, promotion_only: bool = False) -> dict:
    response = requests.get(
        f"{ODOO_API_BASE_URL}/products",
        params={
            "q": query,
            "in_stock_only": in_stock_only,
            "promotion_only": promotion_only,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def human_handoff(reason: str) -> dict:
    return {
        "human_handoff": True,
        "reason": reason,
        "queue": "store_support",
        "message": "I will connect you with a store team member now.",
    }


def should_handoff(message: str) -> bool:
    text = message.casefold()
    return any(word in text for word in FRUSTRATION_WORDS)


def extract_search_query(message: str) -> str:
    cleaned = re.sub(
        r"\b(any|do you have|have you got|is there|where is|where can i find|can i find|price of|promo|promos|promotion|promotions|discount|discounts|deal|deals|stock|available|in stock|on|for)\b",
        " ",
        message,
        flags=re.I,
    )
    cleaned = re.sub(r"[^a-zA-Z0-9\- ]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    cleaned = " ".join(
        word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
        for word in cleaned.split()
    )
    return cleaned or message


def format_inventory_reply(products: list[dict], original_message: str) -> str:
    if not products:
        return (
            "I could not find a matching item in the store inventory. "
            "I can connect you with a human agent if you want me to check manually."
        )

    lines = []
    for product in products[:3]:
        status = "in stock" if product["stock_level"] > 0 else "currently out of stock"
        promos = ", ".join(product["active_promotions"]) if product["active_promotions"] else "No active promotion"
        lines.append(
            f"- {product['name']} ({product['product_id']}): {status}, "
            f"{product['stock_level']} units, ${product['price']:.2f}, "
            f"{product['location_in_store']}. Promo: {promos}."
        )

    intro = "Here is what I found in inventory:"
    if len(products) > 3:
        lines.append(f"...and {len(products) - 3} more result(s).")
    return intro + "\n" + "\n".join(lines)


def run_local_agent(message: str) -> AgentResult:
    if should_handoff(message):
        result = human_handoff("Customer requested a person or showed frustration.")
        return AgentResult(
            reply=result["message"],
            human_handoff=True,
            tool_calls=[{"name": "human_handoff", "arguments": {"reason": result["reason"]}}],
        )

    query = extract_search_query(message)
    wants_promo = "promo" in message.casefold() or "discount" in message.casefold() or "deal" in message.casefold()
    wants_stock = "stock" in message.casefold() or "available" in message.casefold() or "have" in message.casefold()
    inventory = search_inventory(query=query, in_stock_only=wants_stock, promotion_only=wants_promo)
    if wants_stock and not inventory["products"]:
        inventory = search_inventory(query=query, in_stock_only=False, promotion_only=wants_promo)

    return AgentResult(
        reply=format_inventory_reply(inventory["products"], message),
        human_handoff=False,
        tool_calls=[
            {
                "name": "search_inventory",
                "arguments": {
                    "query": query,
                    "in_stock_only": wants_stock,
                    "promotion_only": wants_promo,
                },
            }
        ],
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": "Search the store inventory from the mock Odoo API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product, category, SKU, or store location to search."},
                    "in_stock_only": {"type": "boolean"},
                    "promotion_only": {"type": "boolean"},
                },
                "required": ["query", "in_stock_only", "promotion_only"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "human_handoff",
            "description": "Escalate the conversation to a human support agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the customer needs a human."}
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]


def run_openai_agent(message: str) -> AgentResult:
    from openai import OpenAI

    client = OpenAI()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a WhatsApp support bot for a physical retail store. "
                "Use tools for inventory facts. If the user asks for a human or sounds frustrated, "
                "call human_handoff. Be concise and friendly."
            ),
        },
        {"role": "user", "content": message},
    ]

    first = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    assistant_message = first.choices[0].message
    tool_calls = assistant_message.tool_calls or []

    if not tool_calls:
        return AgentResult(reply=assistant_message.content or "", human_handoff=False, tool_calls=[])

    messages.append(assistant_message)
    executed_calls: list[dict[str, Any]] = []
    handoff = False

    for call in tool_calls:
        args = json.loads(call.function.arguments or "{}")
        if call.function.name == "search_inventory":
            output = search_inventory(**args)
        elif call.function.name == "human_handoff":
            output = human_handoff(**args)
            handoff = True
        else:
            output = {"error": f"Unknown tool {call.function.name}"}

        executed_calls.append({"name": call.function.name, "arguments": args, "output": output})
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(output),
            }
        )

    second = client.chat.completions.create(model=OPENAI_MODEL, messages=messages)
    reply = second.choices[0].message.content or "I will connect you with a store team member now."
    return AgentResult(reply=reply, human_handoff=handoff, tool_calls=executed_calls)


def run_agent(message: str) -> AgentResult:
    if USE_OPENAI and os.getenv("OPENAI_API_KEY"):
        return run_openai_agent(message)
    return run_local_agent(message)
