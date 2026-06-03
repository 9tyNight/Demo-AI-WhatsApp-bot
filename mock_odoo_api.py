from pathlib import Path
from typing import Optional
import json

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_agent import run_agent

app = FastAPI(title="Mock Odoo Inventory API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = Path(__file__).parent / "data" / "inventory.json"


class ChatRequest(BaseModel):
    message: str


def load_inventory() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "mock-odoo-api"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    result = run_agent(request.message)
    return {
        "reply": result.reply,
        "human_handoff": result.human_handoff,
        "tool_calls": result.tool_calls,
    }


@app.get("/products")
def list_products(
    q: Optional[str] = Query(default=None, description="Search term"),
    in_stock_only: bool = False,
    promotion_only: bool = False,
) -> dict:
    products = load_inventory()

    if q:
        needle = q.casefold()
        products = [
            product
            for product in products
            if needle in product["name"].casefold()
            or needle in product["product_id"].casefold()
            or needle in product["location_in_store"].casefold()
        ]

    if in_stock_only:
        products = [product for product in products if product["stock_level"] > 0]

    if promotion_only:
        products = [product for product in products if product["active_promotions"]]

    return {"count": len(products), "products": products}


@app.get("/products/{product_id}")
def get_product(product_id: str) -> dict:
    for product in load_inventory():
        if product["product_id"].casefold() == product_id.casefold():
            return product
    return {"error": "not_found", "message": f"No product found for {product_id}"}
