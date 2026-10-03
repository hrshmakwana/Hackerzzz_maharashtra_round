"""In-memory ShopOps world: customers, orders, policy docs, inbox and outbox.

The mutable part of the world is a plain dict so it can be snapshotted into a checkpoint
and restored exactly. Policy documents are static and live in ``POLICY_DOCS``.
"""

from __future__ import annotations

import copy
import math
import re
from collections import Counter
from datetime import date

TODAY = date(2026, 9, 20)

FIRST_NAMES = [
    "Priya", "Arjun", "Ananya", "Rohan", "Kavya", "Vikram", "Sneha", "Aditya", "Meera",
    "Karan", "Isha", "Nikhil", "Pooja", "Rahul", "Divya", "Siddharth", "Neha", "Aman",
    "Tanvi", "Varun", "Riya", "Harsh", "Shreya", "Manav",
]
LAST_NAMES = [
    "Shah", "Mehta", "Iyer", "Desai", "Nair", "Rao", "Kulkarni", "Joshi", "Pillai",
    "Malhotra", "Verma", "Gupta", "Reddy", "Bhat", "Menon", "Kapoor", "Patil", "Chopra",
    "Sinha", "Banerjee",
]
MAIL_DOMAINS = ["inboxmail.in", "mailbox.co.in", "postmail.in"]
STREETS = [
    "MG Road", "Linking Road", "FC Road", "Park Street", "Brigade Road", "Anna Salai",
    "Baner Road", "Hill Road", "Residency Road", "Station Road", "Lake View Road",
    "Temple Street",
]
CITIES = [
    ("Pune", "411001"), ("Mumbai", "400050"), ("Bengaluru", "560001"), ("Chennai", "600002"),
    ("Hyderabad", "500033"), ("Kolkata", "700016"), ("Delhi", "110054"),
    ("Ahmedabad", "380009"), ("Jaipur", "302001"), ("Kochi", "682011"),
]
CATALOG = [
    ("SKU-KRT-01", "Cotton Kurta", 899),
    ("SKU-SHO-02", "Running Shoes", 2499),
    ("SKU-BTL-03", "Steel Water Bottle", 449),
    ("SKU-EAR-04", "Bluetooth Earbuds", 1799),
    ("SKU-BAG-05", "Laptop Backpack", 1299),
    ("SKU-MUG-06", "Ceramic Mug Set", 649),
    ("SKU-LMP-07", "Desk Lamp", 1149),
    ("SKU-YGA-08", "Yoga Mat", 799),
    ("SKU-CSE-09", "Phone Case", 399),
    ("SKU-CLK-10", "Wall Clock", 999),
    ("SKU-BED-11", "Bedsheet Set", 1499),
    ("SKU-CKR-12", "Pressure Cooker", 2199),
]
SUPPORT_LEAD = "support-lead@shopops.in"


def money(x: float) -> str:
    return f"₹{x:,.2f}"


# ---------------------------------------------------------------- policy documents

POLICY_DOCS: list[dict] = [
    {
        "doc_id": "refund-v1", "topic": "refund", "version": "v1", "status": "archived",
        "updated": "2023-04-01", "title": "Refund policy (v1)",
        "text": "Refund policy v1, effective 2023. Refund requests are accepted within 14 days "
                "of delivery. A restocking fee of 20% is deducted from every refund.",
    },
    {
        "doc_id": "refund-v2", "topic": "refund", "version": "v2", "status": "archived",
        "updated": "2024-06-15", "title": "Refund policy (v2)",
        "text": "Refund policy v2, effective 2024. Refund requests are accepted within 21 days "
                "of delivery. A restocking fee of 15% is deducted from every refund.",
    },
    {
        "doc_id": "refund-v3", "topic": "refund", "version": "v3", "status": "current",
        "updated": "2025-11-01", "title": "Refund policy (v3)",
        "text": "Refund policy v3, effective 2025. Refund requests are accepted within 30 days "
                "of delivery. A restocking fee of 10% is deducted from every refund. Orders "
                "that have not been delivered cannot be refunded; cancel them instead.",
    },
    {
        "doc_id": "cancel-v1", "topic": "cancellation", "version": "v1", "status": "archived",
        "updated": "2023-02-10", "title": "Cancellation policy (v1)",
        "text": "Cancellation policy v1, effective 2023. Orders can be cancelled while they are "
                "processing or shipped. Send the customer a confirmation email.",
    },
    {
        "doc_id": "cancel-v2", "topic": "cancellation", "version": "v2", "status": "current",
        "updated": "2025-08-20", "title": "Cancellation policy (v2)",
        "text": "Cancellation policy v2, effective 2025. Orders can be cancelled only while "
                "they are processing. Shipped or delivered orders cannot be cancelled; reply "
                "to the customer explaining why. Always confirm by email.",
    },
    {
        "doc_id": "address-v1", "topic": "address", "version": "v1", "status": "archived",
        "updated": "2023-05-05", "title": "Shipping address policy (v1)",
        "text": "Shipping address policy v1, effective 2023. The shipping address of an order "
                "can be changed any time before delivery.",
    },
    {
        "doc_id": "address-v2", "topic": "address", "version": "v2", "status": "current",
        "updated": "2025-07-01", "title": "Shipping address policy (v2)",
        "text": "Shipping address policy v2, effective 2025. The shipping address can be "
                "changed only while the order is processing. Once an order has shipped its "
                "address cannot be changed. Confirm every change to the customer by email.",
    },
    {
        "doc_id": "discount-v1", "topic": "discount", "version": "v1", "status": "archived",
        "updated": "2024-10-01", "title": "Festive discount (v1)",
        "text": "Festive discount v1, effective 2024. 10% off on orders of ₹2,000 or more.",
    },
    {
        "doc_id": "discount-v2", "topic": "discount", "version": "v2", "status": "current",
        "updated": "2025-09-15", "title": "Festive discount (v2)",
        "text": "Festive discount v2, effective 2025. 15% off on orders of ₹1,500 or more. "
                "Gold members get an extra 5% off. Orders below ₹1,500 get no discount.",
    },
    {
        "doc_id": "damage-v1", "topic": "damage", "version": "v1", "status": "archived",
        "updated": "2023-09-12", "title": "Damaged item policy (v1)",
        "text": "Damaged item policy v1, effective 2023. Damaged items reported within 15 days "
                "of delivery get a full refund. Otherwise escalate to support-lead@shopops.in.",
    },
    {
        "doc_id": "damage-v2", "topic": "damage", "version": "v2", "status": "current",
        "updated": "2025-10-05", "title": "Damaged item policy (v2)",
        "text": "Damaged item policy v2, effective 2025. Damaged items reported within 7 days "
                "of delivery get a full refund. Otherwise escalate the complaint to "
                "support-lead@shopops.in and tell the customer it has been escalated.",
    },
    {
        "doc_id": "shipping-times-v1", "topic": "shipping_times", "version": "v1",
        "status": "current", "updated": "2025-01-10", "title": "Delivery times",
        "text": "Delivery times store policy. Standard delivery takes 3 to 5 business days. "
                "Express delivery takes 1 to 2 business days in metro cities.",
    },
    {
        "doc_id": "loyalty-v1", "topic": "loyalty", "version": "v1", "status": "current",
        "updated": "2025-03-02", "title": "Loyalty tiers",
        "text": "Loyalty store policy. Customers become Gold members after 10 orders in a year. "
                "Gold membership is reviewed every January.",
    },
    {
        "doc_id": "warranty-v1", "topic": "warranty", "version": "v1", "status": "current",
        "updated": "2024-12-01", "title": "Warranty",
        "text": "Warranty store policy. Electronics carry a 6 month manufacturer warranty. "
                "Warranty claims are handled by the brand service centre.",
    },
]
DOCS_BY_ID = {d["doc_id"]: d for d in POLICY_DOCS}


def current_doc_for_topic(topic: str) -> dict | None:
    for d in POLICY_DOCS:
        if d["topic"] == topic and d["status"] == "current":
            return d
    return None


# ------------------------------------------------------------------- tf-idf index

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _doc_text(d: dict) -> str:
    return f"{d['title']} {d['topic']} {d['text']}"


_DF = Counter(t for d in POLICY_DOCS for t in set(tokenize(_doc_text(d))))
_N = len(POLICY_DOCS)


def _idf(t: str) -> float:
    return math.log((1 + _N) / (1 + _DF.get(t, 0))) + 1.0


def _vec(tokens: list[str]) -> dict[str, float]:
    tf = Counter(tokens)
    v = {t: (1 + math.log(c)) * _idf(t) for t, c in tf.items()}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / norm for t, x in v.items()}


_DOC_VECS = {d["doc_id"]: _vec(tokenize(_doc_text(d))) for d in POLICY_DOCS}


FRESHNESS_BOOST = 0.18


def score_doc(query: str, doc_id: str) -> float:
    """Cosine similarity plus a freshness boost for documents still in force."""
    q = _vec(tokenize(query))
    dv = _DOC_VECS[doc_id]
    cos = sum(w * dv.get(t, 0.0) for t, w in q.items())
    if cos > 0 and DOCS_BY_ID[doc_id]["status"] == "current":
        cos += FRESHNESS_BOOST
    return round(cos, 4)


def search_docs(query: str) -> list[tuple[float, dict]]:
    """Rank all docs for a query. Current versions win exact ties."""
    ranked = []
    for d in POLICY_DOCS:
        s = score_doc(query, d["doc_id"])
        ranked.append((s, 1 if d["status"] == "current" else 0, d["doc_id"], d))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return [(r[0], r[3]) for r in ranked]


def doc_view(d: dict, score: float) -> dict:
    return {
        "doc_id": d["doc_id"],
        "title": d["title"],
        "topic": d["topic"],
        "version": d["version"],
        "status": d["status"],
        "updated": d["updated"],
        "score": score,
        "text": d["text"],
    }


# ------------------------------------------------------------------------ world


class World:
    """Wraps the mutable world dict."""

    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def from_snapshot(cls, snap: dict) -> "World":
        return cls(copy.deepcopy(snap))

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)

    @property
    def today(self) -> str:
        return self.data["today"]

    @property
    def customers(self) -> dict:
        return self.data["customers"]

    @property
    def orders(self) -> dict:
        return self.data["orders"]

    @property
    def inbox(self) -> dict:
        return self.data["inbox"]

    def next_id(self, kind: str) -> int:
        self.data["counters"][kind] = self.data["counters"].get(kind, 0) + 1
        return self.data["counters"][kind]

    def customer_by_email(self, email: str) -> dict | None:
        email = email.strip().lower()
        for c in self.customers.values():
            if c["email"].lower() == email:
                return c
        return None


def make_address(rng) -> str:
    city, pin = rng.choice(CITIES)
    return f"{rng.randint(2, 220)} {rng.choice(STREETS)}, {city} {pin}"


def empty_world() -> dict:
    return {
        "today": TODAY.isoformat(),
        "customers": {},
        "orders": {},
        "inbox": {},
        "outbox": [],
        "refunds": [],
        "cancellations": [],
        "address_log": [],
        "counters": {},
    }
