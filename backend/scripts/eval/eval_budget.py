"""Fail-closed, persistent offline-evaluation budget. No provider I/O on import.

Reservations survive crashes. Unknown usage costs the full reservation. This
protects this runner, not other applications using the same billing account.
"""
import json
import math
import re
import sqlite3
import uuid
import contextvars
from contextlib import contextmanager
from pathlib import Path

LIMITS = {"probe": .05, "development": .05, "comparison": 2.6, "judge": 2.2, "browser": .10}
TOTAL = 5.
BATCH_RESERVATION = contextvars.ContextVar("prepaid_eval_batch", default=None)
PRICES = {"gemini-3.8-flash": (.75, 3.75),
          "gemini-3.1-flash-lite": (.25, 1.5),
          "gemini-3.1-pro-preview": (2., 12.), "gemini-embedding-2": (.2, 0.)}


class BudgetStop(BaseException):
    """Not an Exception: retrieval fallback/retry handlers must not swallow it."""


def micros(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise BudgetStop("Invalid cost")
    return math.ceil(value * 1_000_000)


class Budget:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS costs (id TEXT PRIMARY KEY, stage TEXT NOT NULL, amount INTEGER NOT NULL, settled INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS stop (reason TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS batch_jobs (ticket TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, usage_hash TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, stage, amount, *, check_only=False):
        if stage not in LIMITS:
            raise BudgetStop("Unknown budget stage")
        amount = micros(amount)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM stop LIMIT 1").fetchone():
                raise BudgetStop("Campaign stopped; inspect ledger before starting another campaign")
            total = db.execute("SELECT COALESCE(SUM(amount),0) FROM costs").fetchone()[0]
            used = db.execute("SELECT COALESCE(SUM(amount),0) FROM costs WHERE stage=?", (stage,)).fetchone()[0]
            if total + amount > micros(TOTAL) or used + amount > micros(LIMITS[stage]):
                db.execute("INSERT INTO stop(reason) VALUES(?)", ("Budget exhausted: " + stage,))
                db.commit()
                raise BudgetStop("Budget exhausted: " + stage)
            if check_only:
                return None
            ticket = uuid.uuid4().hex
            db.execute("INSERT INTO costs(id,stage,amount) VALUES(?,?,?)", (ticket, stage, amount))
        return ticket

    def settle(self, ticket, actual):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT amount,settled FROM costs WHERE id=?", (ticket,)).fetchone()
            if row is None or row[1]:
                raise BudgetStop("Unknown or already settled reservation")
            amount = row[0] if actual is None else micros(actual)
            if amount > row[0]:
                # Retain true cost even if the provider violated the assumed bound.
                db.execute("UPDATE costs SET amount=?,settled=1 WHERE id=?", (amount, ticket))
                db.execute("INSERT INTO stop(reason) VALUES('Provider usage exceeded reservation')")
                db.commit()
                raise BudgetStop("Provider usage exceeded reservation; stop")
            db.execute("UPDATE costs SET amount=?,settled=1 WHERE id=?", (amount, ticket))

    def summary(self):
        with self.connect() as db:
            stages = dict(db.execute("SELECT stage,SUM(amount)/1000000.0 FROM costs GROUP BY stage"))
            stopped = db.execute("SELECT reason FROM stop LIMIT 1").fetchone()
        return {"committed_usd": sum(stages.values()), "stages": stages, "total_limit_usd": TOTAL,
                "stopped": bool(stopped), "stop_reason": stopped[0] if stopped else None}

    def available(self, stage):
        """Read-only planning; the actual reservation still checks atomically."""
        if stage not in LIMITS:
            raise BudgetStop("Unknown budget stage")
        snapshot = self.summary()
        if snapshot["stopped"]:
            raise BudgetStop("Campaign stopped")
        return max(0, min(TOTAL-snapshot["committed_usd"], LIMITS[stage]-snapshot["stages"].get(stage, 0)))

    def bind_batch(self, ticket, name):
        if not isinstance(name, str) or not name:
            raise BudgetStop("Missing provider batch identity")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cost = db.execute("SELECT stage,settled FROM costs WHERE id=?", (ticket,)).fetchone()
            old = db.execute("SELECT name FROM batch_jobs WHERE ticket=?", (ticket,)).fetchone()
            if not cost or cost[0] != "judge" or (cost[1] and not old) or (old and old[0] != name):
                raise BudgetStop("Batch reservation identity mismatch")
            if not old:
                db.execute("INSERT INTO batch_jobs(ticket,name) VALUES(?,?)", (ticket, name))

    def settle_batch(self, ticket, name, actual, usage_hash):
        """Idempotent actual-usage settlement, including after process restart."""
        if actual is None:
            return False  # Never release unknown charges; allow later verified collection.
        amount = micros(actual)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT c.amount,c.settled,b.name,b.usage_hash FROM costs c JOIN batch_jobs b ON c.id=b.ticket WHERE c.id=?", (ticket,)).fetchone()
            if row is None or row[2] != name:
                raise BudgetStop("Batch reservation identity mismatch")
            if row[1]:
                if row[0] != amount or row[3] != usage_hash:
                    db.execute("INSERT INTO stop(reason) VALUES('Conflicting batch settlement')")
                    db.commit()
                    raise BudgetStop("Conflicting batch settlement")
                return True
            db.execute("UPDATE costs SET amount=?,settled=1 WHERE id=?", (amount, ticket))
            db.execute("UPDATE batch_jobs SET usage_hash=? WHERE ticket=?", (usage_hash, ticket))
            if amount > row[0]:
                db.execute("INSERT INTO stop(reason) VALUES('Provider usage exceeded reservation')")
                db.commit()
                raise BudgetStop("Provider usage exceeded reservation; stop")
        return True


def request_bound(path, body):
    model = re.search(r"models/([^/:]+):", path)
    if not model or model[1] not in PRICES:
        raise BudgetStop("Unpriced endpoint/model blocked")
    incoming, outgoing = PRICES[model[1]]
    if path.endswith(":batchGenerateContent"):
        try:
            entries = body["batch"]["inputConfig"]["requests"]["requests"]
            if not entries:
                raise KeyError("empty batch")
            return sum(request_bound("models/" + model[1] + ":generateContent", entry["request"]) for entry in entries) * .5
        except (KeyError, TypeError):
            raise BudgetStop("Only inline, fully priced batches allowed")
    if not any(path.endswith(s) for s in (":generateContent", ":embedContent", ":batchEmbedContents")):
        raise BudgetStop("Unsupported billable endpoint")
    if (model[1] == "gemini-embedding-2") != ("embedContent" in path or "batchEmbedContents" in path):
        raise BudgetStop("Model/operation price mismatch")
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    # Text only. External tools, cached content and media may carry unpriced fees.
    if any(key in encoded for key in (b'"cachedContent"', b'"inlineData"', b'"fileData"')):
        raise BudgetStop("Unpriced tool/media/cached input blocked")
    # LangChain structured output uses a function declaration, without executing
    # an external service. Its schema is already included in the input bound.
    if any(not isinstance(tool, dict) or set(tool) != {"functionDeclarations"}
           or not tool["functionDeclarations"] for tool in body.get("tools", [])):
        raise BudgetStop("Unpriced external tool blocked")
    output = 0
    if path.endswith(":generateContent"):
        config = body.get("generationConfig", {})
        output = config.get("maxOutputTokens")
        if type(output) is not int or not 0 < output <= 8192 or config.get("candidateCount", 1) != 1:
            raise BudgetStop("Explicit output cap <=8192 and one candidate required")
        thinking = config.get("thinkingConfig", {}).get("thinkingBudget", 0)
        if type(thinking) is not int or thinking < 0:
            raise BudgetStop("Unbounded thinking budget")
        output += thinking
    # Conservative byte proxy plus protocol overhead; no paid token-count call.
    return ((len(encoded) + 2048) * incoming + output * outgoing) / 1e6


def response_cost(path, response):
    if path.endswith(":batchGenerateContent"):
        return None  # Keep entire submitted-job reservation across collection/restarts.
    try:
        body = json.loads(response.body)
        usage = body.get("usageMetadata")
        if usage is None and "embeddings" in body:
            return None
        incoming = usage["promptTokenCount"]
        outgoing = (usage["candidatesTokenCount"] + usage.get("thoughtsTokenCount", 0)
                    if path.endswith(":generateContent") else 0)
        if any(type(n) is not int or n < 0 for n in (incoming, outgoing)):
            return None
        model = re.search(r"models/([^/:]+):", path)[1]
        i, o = PRICES[model]
        return (incoming * i + outgoing * o) / 1e6
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def install_transport_guard(budget, stage, client_class=None):
    if client_class is None:
        from google.genai._api_client import BaseApiClient
        client_class = BaseApiClient
    original = client_class.request
    original_async = client_class.async_request

    def single_attempt(options):
        # SDK retry attempts happen below request(), so prevent hidden billable
        # attempts. Any outer retry passes the reservation gate again.
        if options is not None and hasattr(options, "model_dump"):
            options = options.model_dump(exclude_none=True)
        return {**(options or {}), "retry_options": {"attempts": 1}}

    def reserve(method, path, body):
        if method.lower() == "get":
            return None  # Job status/collection; no model generation.
        bound = request_bound(path, body)
        prepaid = BATCH_RESERVATION.get() if path.endswith(":batchGenerateContent") else None
        if prepaid is not None:
            if prepaid["ledger"] != budget.path or stage != "judge" or prepaid["used"] or micros(bound) > prepaid["micros"]:
                raise BudgetStop("Prepaid batch request mismatch or duplicate transport")
            prepaid["used"] = True
            return prepaid["ticket"]
        return budget.reserve(stage, bound)

    def guarded(client, method, path, request_dict, http_options=None):
        ticket = reserve(method, path, request_dict)
        try:
            response = original(client, method, path, request_dict, single_attempt(http_options))
        except BaseException:
            if ticket and not path.endswith(":batchGenerateContent"): budget.settle(ticket, None)
            raise
        if ticket and not path.endswith(":batchGenerateContent"): budget.settle(ticket, response_cost(path, response))
        return response

    async def guarded_async(client, method, path, request_dict, http_options=None):
        ticket = reserve(method, path, request_dict)
        try:
            response = await original_async(client, method, path, request_dict, single_attempt(http_options))
        except BaseException:
            if ticket and not path.endswith(":batchGenerateContent"): budget.settle(ticket, None)
            raise
        if ticket and not path.endswith(":batchGenerateContent"): budget.settle(ticket, response_cost(path, response))
        return response

    client_class.request = guarded
    client_class.async_request = guarded_async
    # Stream APIs are not used by these experiments and cannot bypass accounting.
    def no_stream(*args, **kwargs):
        raise BudgetStop("Streaming is not budgeted by this evaluator")
    client_class.request_streamed = no_stream
    client_class.async_request_streamed = no_stream


def add_budget_args(parser):
    parser.add_argument("--allow-paid", action="store_true", help="Explicit paid-run authorization; default is offline")
    parser.add_argument("--budget-ledger", default=str(Path(__file__).resolve().parents[3]/"tmp/eval-budget.sqlite"))


def preflight_batch_judge(budget, *, pairs, output_cap=2048, chunk_size=10):
    """Reject impossible final-judge plans before spending on new answers.

    This is the output-only reservation floor, not an actual charge or complete
    input estimate. Passing still requires full-payload reservation at submit.
    """
    if type(pairs) is not int or pairs <= 0 or type(output_cap) is not int or output_cap <= 0 or type(chunk_size) is not int or chunk_size <= 0:
        raise BudgetStop("Invalid judge plan")
    minimum = min(pairs, chunk_size) * output_cap * PRICES["gemini-3.1-pro-preview"][1] * .5 / 1e6
    budget.reserve("judge", minimum, check_only=True)


def activate_budget(args, stage):
    if not args.allow_paid:
        raise BudgetStop("Offline default: no API calls. Paid runs require --allow-paid")
    ledger = Budget(args.budget_ledger)
    install_transport_guard(ledger, stage)
    return ledger
