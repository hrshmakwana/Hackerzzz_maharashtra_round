"""Five task families, templated with random entities per seed.

``make_task(family, seed)`` builds a fresh world plus the task the agent sees. The
``truth`` field is the expected outcome under the *current* store policy; only the
checker reads it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .world import (
    CATALOG,
    FIRST_NAMES,
    LAST_NAMES,
    MAIL_DOMAINS,
    SUPPORT_LEAD,
    TODAY,
    empty_world,
    make_address,
    money,
)

FAMILIES = ["refund", "address_change", "discount_quote", "cancel", "complaint_triage"]
TRAIN_FAMILIES = FAMILIES[:4]
HELDOUT_FAMILY = "complaint_triage"

# Current policy numbers, used to compute ground truth.
REFUND_WINDOW, RESTOCK_FEE = 30, 10
DISCOUNT_THRESHOLD, DISCOUNT_PCT, GOLD_EXTRA = 1500, 15, 5
DAMAGE_WINDOW = 7


@dataclass
class Task:
    family: str
    task_id: str
    seed: int
    text: str
    email_id: str
    truth: dict = field(default_factory=dict)


def task_rng(family: str, seed: int) -> random.Random:
    return random.Random(f"task:{family}:{seed}")


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _items(rng: random.Random, min_total: int = 0, max_total: int = 10**9) -> list[dict]:
    for _ in range(50):
        picks = rng.sample(CATALOG, rng.randint(1, 3))
        items = [{"sku": s, "name": n, "price": p, "qty": 2 if rng.random() < 0.2 else 1}
                 for s, n, p in picks]
        total = sum(i["price"] * i["qty"] for i in items)
        if min_total <= total <= max_total:
            return items
    return items


def _order(oid: str, cid: str, items: list[dict], status: str, address: str,
           rng: random.Random, delivered_ago: int | None = None) -> dict:
    if status == "delivered":
        d_ago = delivered_ago if delivered_ago is not None else rng.randint(2, 45)
        delivered = _d(d_ago)
        placed = _d(d_ago + rng.randint(2, 6))
    elif status == "shipped":
        delivered, placed = None, _d(rng.randint(1, 4))
    else:  # processing
        delivered, placed = None, _d(rng.randint(0, 1))
    return {
        "order_id": oid,
        "customer_id": cid,
        "items": items,
        "amount": float(sum(i["price"] * i["qty"] for i in items)),
        "placed": placed,
        "delivered": delivered,
        "status": status,
        "shipping_address": address,
    }


def _people(rng: random.Random, n: int) -> list[dict]:
    names, ids, out = set(), set(), []
    while len(out) < n:
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        cid = f"C-{rng.randint(1000, 9999)}"
        if (first, last) in names or cid in ids:
            continue
        names.add((first, last))
        ids.add(cid)
        out.append({
            "customer_id": cid,
            "name": f"{first} {last}",
            "first": first,
            "email": f"{first.lower()}.{last.lower()}@{rng.choice(MAIL_DOMAINS)}",
            "tier": "gold" if rng.random() < 0.3 else "standard",
            "order_ids": [],
            "address": make_address(rng),
        })
    return out


def _build_world(rng: random.Random, target: dict) -> tuple[dict, dict, dict]:
    """Create customers and orders. ``target`` describes the order the task is about:
    {"status", "delivered_ago", "min_total", "max_total", "tier"}. Order ids are
    consecutive across customers so every order has real neighbours."""
    world = empty_world()
    people = _people(rng, rng.randint(4, 6))
    me = people[0]
    if target.get("tier"):
        me["tier"] = target["tier"]

    specs = [("target", me)]
    for p in people:
        for _ in range(rng.randint(1, 2) if p is not me else rng.randint(0, 2)):
            specs.append(("other", p))
    rng.shuffle(specs)

    base = rng.randint(1100, 8800)
    target_order = None
    for i, (kind, person) in enumerate(specs):
        oid = str(base + i)
        if kind == "target":
            items = _items(rng, target.get("min_total", 0), target.get("max_total", 10**9))
            o = _order(oid, person["customer_id"], items, target["status"], person["address"],
                       rng, target.get("delivered_ago"))
            target_order = o
        else:
            status = rng.choice(["delivered", "delivered", "shipped", "processing"])
            o = _order(oid, person["customer_id"], _items(rng), status, person["address"], rng)
        world["orders"][oid] = o
        person["order_ids"].append(oid)

    for p in people:
        world["customers"][p["customer_id"]] = {
            k: p[k] for k in ("customer_id", "name", "email", "tier", "order_ids")
        }
    return world, me, target_order


def _add_noise_emails(world: dict, rng: random.Random, people_pool: list[dict],
                      taken: set[str]) -> None:
    subjects = [
        ("Where is my parcel?", "Hi, can you tell me when my parcel will arrive? Thanks."),
        ("Invoice copy", "Hello, please share a GST invoice for my last purchase."),
        ("Great service", "Just wanted to say the delivery was quick. Thank you!"),
    ]
    for subject, body in rng.sample(subjects, rng.randint(1, 2)):
        eid = _email_id(rng, taken)
        sender = rng.choice(people_pool)
        world["inbox"][eid] = {"email_id": eid, "from": sender["email"], "subject": subject,
                               "body": body, "received": _d(rng.randint(0, 3))}


def _email_id(rng: random.Random, taken: set[str]) -> str:
    while True:
        eid = f"E-{rng.randint(100, 999)}"
        if eid not in taken:
            taken.add(eid)
            return eid


def make_task(family: str, seed: int) -> tuple[Task, dict]:
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family}")
    rng = task_rng(family, seed)
    today = TODAY.isoformat()

    if family == "refund":
        eligible = rng.random() < 0.72
        d_ago = rng.randint(2, REFUND_WINDOW) if eligible else rng.randint(REFUND_WINDOW + 1, 42)
        world, me, order = _build_world(rng, {"status": "delivered", "delivered_ago": d_ago})
    elif family == "address_change":
        status = "processing" if rng.random() < 0.68 else "shipped"
        world, me, order = _build_world(rng, {"status": status})
    elif family == "discount_quote":
        big = rng.random() < 0.8
        tier = "gold" if rng.random() < 0.35 else "standard"
        rng_total = {"min_total": 1500} if big else {"max_total": 1499}
        world, me, order = _build_world(rng, {"status": "delivered", "tier": tier, **rng_total})
    elif family == "cancel":
        status = "processing" if rng.random() < 0.62 else "shipped"
        world, me, order = _build_world(rng, {"status": status})
    else:  # complaint_triage
        refund = rng.random() < 0.55
        d_ago = rng.randint(1, DAMAGE_WINDOW) if refund else rng.randint(DAMAGE_WINDOW + 1, 20)
        world, me, order = _build_world(rng, {"status": "delivered", "delivered_ago": d_ago})

    taken: set[str] = set()
    eid = _email_id(rng, taken)
    oid = order["order_id"]
    item = order["items"][0]["name"]
    first = me["first"]
    email = me["email"]
    truth: dict = {"refunds": [], "cancellations": [], "address_changes": {}, "emails": [],
                   "answer": []}

    if family == "refund":
        reason = rng.choice(["it doesn't fit", "it isn't what I expected",
                             "the colour is different from the photos", "I no longer need it"])
        subject = f"Return request for order #{oid}"
        body = (f"Hi ShopOps team,\n\nI received order #{oid} ({item}) on {order['delivered']} "
                f"but {reason}. Could you please process a refund?\n\nThanks,\n{first}")
        text = (f"Today is {today}. Handle the refund request in email {eid} following the "
                f"current refund policy. If the order is eligible, refund it minus the "
                f"restocking fee and email the customer the amount; if not, email them that "
                f"it is not eligible.")
        days = (TODAY - date.fromisoformat(order["delivered"])).days
        if days <= REFUND_WINDOW:
            amt = round(order["amount"] * (1 - RESTOCK_FEE / 100), 2)
            truth["refunds"] = [[oid, amt]]
            truth["emails"] = [{"to": email, "contains": [money(amt)]}]
            truth["answer"] = ["refunded", money(amt)]
        else:
            truth["emails"] = [{"to": email, "contains": ["not eligible"]}]
            truth["answer"] = ["not eligible"]

    elif family == "address_change":
        new_addr = make_address(rng)
        while new_addr == order["shipping_address"]:
            new_addr = make_address(rng)
        subject = f"Change delivery address for order #{oid}"
        body = (f"Hello,\n\nI'm moving next week. Please update the delivery address for order "
                f"#{oid} to:\nNew address: {new_addr}\n\nRegards,\n{first}")
        text = (f"Today is {today}. A customer asked to change the delivery address in email "
                f"{eid}. Follow the current shipping address policy, update the order if it is "
                f"allowed, and confirm to the customer by email.")
        if order["status"] == "processing":
            truth["address_changes"] = {oid: new_addr}
            truth["emails"] = [{"to": email, "contains": [new_addr]}]
            truth["answer"] = ["updated"]
        else:
            truth["emails"] = [{"to": email, "contains": ["already shipped"]}]
            truth["answer"] = ["cannot"]

    elif family == "discount_quote":
        occasion = rng.choice(["Diwali", "a family wedding", "Navratri gifting", "my sister"])
        subject = f"Festive price for re-ordering #{oid}"
        body = (f"Hi,\n\nI'd like to order the same items as my order #{oid} again for "
                f"{occasion}. What would the festive price be?\n\n{first}")
        text = (f"Today is {today}. The customer in email {eid} wants a festive price quote for "
                f"re-ordering the items of a past order. Use the current festive discount "
                f"policy, work out the quote and email it to the customer.")
        subtotal = order["amount"]
        pct = 0
        if subtotal >= DISCOUNT_THRESHOLD:
            pct = DISCOUNT_PCT + (GOLD_EXTRA if me["tier"] == "gold" else 0)
        quote = round(subtotal * (1 - pct / 100), 2)
        truth["emails"] = [{"to": email, "contains": [money(quote)]}]
        truth["answer"] = [money(quote)]

    elif family == "cancel":
        subject = f"Cancel order #{oid}"
        body = (f"Hi,\n\nPlease cancel order #{oid} ({item}), I ordered it by mistake.\n\n"
                f"Thank you,\n{first}")
        text = (f"Today is {today}. Handle the cancellation request in email {eid} according to "
                f"the current cancellation policy and confirm the result to the customer by "
                f"email.")
        if order["status"] == "processing":
            truth["cancellations"] = [oid]
            truth["emails"] = [{"to": email, "contains": ["has been cancelled"]}]
            truth["answer"] = ["cancelled order"]
        else:
            truth["emails"] = [{"to": email, "contains": ["already shipped"]}]
            truth["answer"] = ["cannot cancel"]

    else:  # complaint_triage
        damage = rng.choice(["the box was crushed", "it has a crack on one side",
                             "a part is broken", "it was leaking"])
        subject = f"Damaged item in order #{oid}"
        body = (f"Hi,\n\nThe {item} in my order #{oid} arrived damaged, {damage}. I'd like "
                f"this sorted out.\n\n{first}")
        text = (f"Today is {today}. Triage the complaint in email {eid} using the current "
                f"damaged item policy: refund the full order amount if it qualifies, otherwise "
                f"escalate it to the support lead. Let the customer know by email.")
        days = (TODAY - date.fromisoformat(order["delivered"])).days
        if days <= DAMAGE_WINDOW:
            truth["refunds"] = [[oid, round(order["amount"], 2)]]
            truth["emails"] = [{"to": email, "contains": [money(order["amount"])]}]
            truth["answer"] = ["refunded"]
        else:
            truth["emails"] = [{"to": SUPPORT_LEAD, "contains": [f"#{oid}"]},
                               {"to": email, "contains": ["escalated"]}]
            truth["answer"] = ["escalated"]

    world["inbox"][eid] = {"email_id": eid, "from": email, "subject": subject, "body": body,
                           "received": today}
    others = [{"email": c["email"]} for c in world["customers"].values() if c["email"] != email]
    _add_noise_emails(world, rng, others or [{"email": email}], taken)

    truth["addresses"] = {o_id: o["shipping_address"] for o_id, o in world["orders"].items()}
    truth["addresses"].update(truth["address_changes"])
    truth["order_id"] = oid
    truth["customer_email"] = email

    task = Task(family=family, task_id=f"{family}-{seed}", seed=seed, text=text,
                email_id=eid, truth=truth)
    return task, world
