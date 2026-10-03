"""Tool functions the agent can call. Each one reads or mutates the world.

Tools raise ``ToolError`` for bad input; the runner turns that into the step's error.
They deliberately do not enforce store policy (that is the agent's job), the same way a
back-office API usually trusts the operator calling it.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable

from .world import DOCS_BY_ID, World, doc_view, search_docs


class ToolError(Exception):
    pass


SIDE_EFFECT_TOOLS = {"issue_refund", "update_address", "cancel_order", "send_email"}

TRANSIENT_ERRORS = [
    "TimeoutError: upstream service did not respond in 5s",
    "RateLimited: too many requests, retry shortly",
    "ConnectionReset: connection reset by peer",
    "ServiceUnavailable: backend temporarily unavailable (503)",
]


def _order_id(value: Any) -> str:
    return str(value).strip().lstrip("#")


def _order(world: World, order_id: Any) -> dict:
    oid = _order_id(order_id)
    order = world.orders.get(oid)
    if order is None:
        raise ToolError(f"order {oid} not found")
    return order


def search_customer(world: World, query: str) -> dict:
    q = str(query).strip().lower()
    if not q:
        raise ToolError("empty query")
    match = world.customer_by_email(q) if "@" in q else None
    if match is None and "@" not in q:
        for c in world.customers.values():
            if q in c["name"].lower():
                match = c
                break
    if match is None:
        raise ToolError(f"no customer matches '{query}'")
    return {
        "customer_id": match["customer_id"],
        "name": match["name"],
        "email": match["email"],
        "tier": match["tier"],
        "order_ids": list(match["order_ids"]),
    }


def get_order(world: World, order_id: Any) -> dict:
    o = _order(world, order_id)
    return {
        "order_id": o["order_id"],
        "customer_id": o["customer_id"],
        "items": [dict(i) for i in o["items"]],
        "amount": o["amount"],
        "placed": o["placed"],
        "delivered": o["delivered"],
        "status": o["status"],
        "shipping_address": o["shipping_address"],
    }


def list_orders(world: World, customer_id: str) -> dict:
    c = world.customers.get(str(customer_id))
    if c is None:
        raise ToolError(f"customer {customer_id} not found")
    rows = []
    for oid in c["order_ids"]:
        o = world.orders[oid]
        rows.append({"order_id": oid, "placed": o["placed"], "status": o["status"],
                     "amount": o["amount"]})
    return {"customer_id": c["customer_id"], "orders": rows}


def retrieve_policy(world: World, query: str) -> dict:
    if not str(query).strip():
        raise ToolError("empty query")
    score, doc = search_docs(str(query))[0]
    return doc_view(doc, score)


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ToolError("unsupported expression")


def calculate(world: World, expression: str) -> dict:
    expr = str(expression).replace("₹", "").replace(",", "")
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except (SyntaxError, ZeroDivisionError) as exc:
        raise ToolError(f"cannot evaluate: {exc}") from exc
    return {"expression": str(expression), "result": round(float(value), 2)}


def issue_refund(world: World, order_id: Any, amount: Any) -> dict:
    o = _order(world, order_id)
    try:
        amount = round(float(str(amount).replace("₹", "").replace(",", "")), 2)
    except ValueError as exc:
        raise ToolError("amount must be a number") from exc
    if amount <= 0:
        raise ToolError("amount must be positive")
    if amount > o["amount"] + 0.01:
        raise ToolError(f"refund {amount} exceeds order amount {o['amount']}")
    if any(r["order_id"] == o["order_id"] for r in world.data["refunds"]):
        raise ToolError(f"order {o['order_id']} was already refunded")
    rid = f"R-{9000 + world.next_id('refund')}"
    world.data["refunds"].append({"refund_id": rid, "order_id": o["order_id"], "amount": amount})
    return {"refund_id": rid, "order_id": o["order_id"], "amount": amount, "status": "processed"}


def update_address(world: World, order_id: Any, address: str) -> dict:
    o = _order(world, order_id)
    address = str(address).strip()
    if len(address) < 8:
        raise ToolError("address looks incomplete")
    world.data["address_log"].append(
        {"order_id": o["order_id"], "old": o["shipping_address"], "new": address})
    o["shipping_address"] = address
    return {"order_id": o["order_id"], "shipping_address": address, "status": "updated"}


def cancel_order(world: World, order_id: Any) -> dict:
    o = _order(world, order_id)
    if o["status"] == "cancelled":
        raise ToolError(f"order {o['order_id']} is already cancelled")
    o["status"] = "cancelled"
    world.data["cancellations"].append(o["order_id"])
    return {"order_id": o["order_id"], "status": "cancelled"}


def read_email(world: World, email_id: str) -> dict:
    e = world.inbox.get(str(email_id).strip())
    if e is None:
        raise ToolError(f"email {email_id} not found")
    return dict(e)


def send_email(world: World, to: str, subject: str, body: str) -> dict:
    to = str(to).strip()
    if "@" not in to or "." not in to.split("@")[-1]:
        raise ToolError(f"invalid recipient '{to}'")
    mid = f"M-{500 + world.next_id('message')}"
    world.data["outbox"].append({"message_id": mid, "to": to, "subject": str(subject),
                                 "body": str(body)})
    return {"message_id": mid, "to": to, "status": "sent"}


TOOLS: dict[str, Callable[..., dict]] = {
    "search_customer": search_customer,
    "get_order": get_order,
    "list_orders": list_orders,
    "retrieve_policy": retrieve_policy,
    "calculate": calculate,
    "issue_refund": issue_refund,
    "update_address": update_address,
    "cancel_order": cancel_order,
    "read_email": read_email,
    "send_email": send_email,
}

# JSON-schema style descriptions, shared with the Gemini policy.
TOOL_SPECS: dict[str, dict] = {
    "search_customer": {
        "description": "Find a customer by email address or name.",
        "params": {"query": ("string", "Email address or (part of) the customer's name")},
    },
    "get_order": {
        "description": "Fetch one order with items, amount, dates, status and address.",
        "params": {"order_id": ("string", "Order id, e.g. 1043")},
    },
    "list_orders": {
        "description": "List all orders of a customer.",
        "params": {"customer_id": ("string", "Customer id, e.g. C-4821")},
    },
    "retrieve_policy": {
        "description": "Search the store policy documents and return the best match.",
        "params": {"query": ("string", "What policy you are looking for")},
    },
    "calculate": {
        "description": "Evaluate an arithmetic expression (+ - * / and parentheses).",
        "params": {"expression": ("string", "e.g. 2199 * (1 - 10/100)")},
    },
    "issue_refund": {
        "description": "Refund an amount (in rupees) to an order.",
        "params": {"order_id": ("string", "Order id"), "amount": ("number", "Amount in rupees")},
    },
    "update_address": {
        "description": "Change the shipping address of an order.",
        "params": {"order_id": ("string", "Order id"), "address": ("string", "New address")},
    },
    "cancel_order": {
        "description": "Cancel an order.",
        "params": {"order_id": ("string", "Order id")},
    },
    "read_email": {
        "description": "Read an email from the support inbox.",
        "params": {"email_id": ("string", "Email id, e.g. E-312")},
    },
    "send_email": {
        "description": "Send an email.",
        "params": {"to": ("string", "Recipient address"), "subject": ("string", "Subject"),
                   "body": ("string", "Plain-text body")},
    },
    "finish": {
        "description": "Finish the task with a one-line answer describing what was done.",
        "params": {"answer": ("string", "Final answer")},
    },
}


def execute(world: World, name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        raise ToolError(f"unknown tool '{name}'")
    params = set(TOOL_SPECS[name]["params"])
    extra = set(args) - params
    missing = params - set(args)
    if extra:
        raise ToolError(f"unexpected argument(s): {', '.join(sorted(extra))}")
    if missing:
        raise ToolError(f"missing argument(s): {', '.join(sorted(missing))}")
    return fn(world, **args)


def swap_doc_output(doc_id: str, query: str) -> dict:
    from .world import score_doc

    d = DOCS_BY_ID.get(doc_id)
    if d is None:
        raise ToolError(f"unknown document {doc_id}")
    return doc_view(d, score_doc(query, doc_id))
