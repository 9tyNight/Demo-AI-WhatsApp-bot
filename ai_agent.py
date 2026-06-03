import os
import re
from dataclasses import dataclass, field
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

ODOO_API_BASE_URL = os.getenv("ODOO_API_BASE_URL", "http://127.0.0.1:8000")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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

SYSTEM_INSTRUCTION = """
You are a concise WhatsApp customer support bot for a physical retail store.

Rules:
- For stock, price, location, product, SKU, availability, or promotion questions,
  call search_inventory before answering.
- Never invent product data. Use only tool results for inventory facts.
- Prices are in USD. Format prices with the $ symbol.
- If a customer is frustrated, repeats a complaint, or asks for a human, call
  human_handoff immediately and do not continue trying to solve the issue.
- Keep replies friendly, short, and suitable for WhatsApp.
""".strip()


@dataclass
class AgentResult:
    reply: str
    human_handoff: bool
    tool_calls: list[dict[str, Any]]


@dataclass
class ToolTrace:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, arguments: dict[str, Any], output: dict[str, Any]) -> None:
        self.calls.append({"name": name, "arguments": arguments, "output": output})

    def drain(self) -> list[dict[str, Any]]:
        calls = self.calls[:]
        self.calls.clear()
        return calls


TOOL_TRACE = ToolTrace()


def search_inventory(query: str) -> dict:
    """Search store inventory by product name, SKU, department, location, stock, or promotion."""
    response = requests.get(
        f"{ODOO_API_BASE_URL}/products",
        params={"q": query},
        timeout=10,
    )
    response.raise_for_status()
    result = response.json()
    normalized_query = extract_search_query(query)
    if result.get("count") == 0 and normalized_query != query:
        response = requests.get(
            f"{ODOO_API_BASE_URL}/products",
            params={"q": normalized_query},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()

    TOOL_TRACE.add("search_inventory", {"query": query, "normalized_query": normalized_query}, result)
    return result


def human_handoff(reason: str) -> dict:
    """Escalate the customer to a human store support agent and pause the AI session."""
    result = {
        "human_handoff": True,
        "reason": reason,
        "queue": "store_support",
        "message": "I will connect you with a store team member now.",
    }
    TOOL_TRACE.add("human_handoff", {"reason": reason}, result)
    return result


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


def format_inventory_reply(products: list[dict]) -> str:
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

    if len(products) > 3:
        lines.append(f"...and {len(products) - 3} more result(s).")
    return "Here is what I found in inventory:\n" + "\n".join(lines)


def run_local_agent(message: str) -> AgentResult:
    if should_handoff(message):
        result = human_handoff("Customer requested a person or showed frustration.")
        return AgentResult(reply=result["message"], human_handoff=True, tool_calls=TOOL_TRACE.drain())

    inventory = search_inventory(extract_search_query(message))
    return AgentResult(
        reply=format_inventory_reply(inventory["products"]),
        human_handoff=False,
        tool_calls=TOOL_TRACE.drain(),
    )


class GeminiSupportAgent:
    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        from google import genai
        from google.genai import types

        self.client = genai.Client(api_key=api_key)
        self.chat = self.client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                tools=[search_inventory, human_handoff],
            ),
        )
        self.paused_for_handoff = False

    def send(self, message: str) -> AgentResult:
        if self.paused_for_handoff:
            return AgentResult(
                reply="A human agent is taking over this conversation now.",
                human_handoff=True,
                tool_calls=[],
            )

        if should_handoff(message):
            result = human_handoff("Customer requested a person or showed frustration.")
            self.paused_for_handoff = True
            return AgentResult(reply=result["message"], human_handoff=True, tool_calls=TOOL_TRACE.drain())

        try:
            response = self.chat.send_message(message)
        except Exception as exc:
            TOOL_TRACE.drain()
            fallback = run_local_agent(message)
            fallback.reply = (
                f"{fallback.reply}\n\n"
                "Note: Gemini is temporarily unavailable, so I used the local inventory fallback."
            )
            fallback.tool_calls.append(
                {
                    "name": "gemini_error",
                    "arguments": {"model": GEMINI_MODEL},
                    "output": {"error": str(exc)},
                }
            )
            return fallback

        tool_calls = TOOL_TRACE.drain()
        handoff = any(call["name"] == "human_handoff" for call in tool_calls)
        if handoff:
            self.paused_for_handoff = True

        return AgentResult(
            reply=response.text or "I will connect you with a store team member now.",
            human_handoff=handoff,
            tool_calls=tool_calls,
        )

    def history(self) -> list[Any]:
        return self.chat.get_history()


_GEMINI_AGENT: GeminiSupportAgent | None = None


def get_gemini_agent() -> GeminiSupportAgent:
    global _GEMINI_AGENT
    if _GEMINI_AGENT is None:
        _GEMINI_AGENT = GeminiSupportAgent()
    return _GEMINI_AGENT


def run_agent(message: str) -> AgentResult:
    if os.environ.get("GEMINI_API_KEY"):
        return get_gemini_agent().send(message)
    return run_local_agent(message)
