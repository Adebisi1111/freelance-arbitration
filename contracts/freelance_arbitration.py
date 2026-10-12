# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Freelance Arbitration Contract.

A client records an escrow amount and defines plain-language rules. The
freelancer submits a link to their completed work. The leader reviews the work
against the rules and each validator INDEPENDENTLY fetches the same work and
reaches its own verdict, agreeing only if it reproduces the leader's verdict.
On consensus the contract records a binding arbitration decision: the work is
approved ("True") or rejected ("False").

Consensus uses gl.vm.run_nondet with a leader/validator pair — the pattern
verified working on Bradbury — NOT gl.eq_principle.strict_eq over an LLM output.
strict_eq does not enforce cross-validator equality for non-deterministic LLM
results, so a fabricated or divergent leader verdict would commit unchecked.
Here every validator re-derives the verdict independently.

Value settlement note: the value-moving primitive (gl.pay / emit_transfer) does
not settle on this network — verified on-chain with a minimal payable echo-pay
probe that returned FINISHED_WITH_ERROR with zero executions. The escrow is
therefore recorded as a durable, consensus-derived obligation rather than a
transfer: the arbitration DECISION is the binding on-chain artifact, and any
actual payout is settled off-chain against that decision. This is stated plainly
rather than dressed up as a working payout path.
"""

import json
import re
from datetime import datetime, timezone

from genlayer import *


def _review(url: str, rules: str) -> dict:
    """Fetch the submitted work and judge it against the rules.

    Module-level so both leader and validators run the identical code path.
    Returns exactly {"verdict": "True"|"False"} so the comparison is a plain
    string equality — no fuzzy scoring for a leader to drift on.
    """
    response = gl.nondet.web.request(url, method="GET")
    body = response.body if hasattr(response, "body") else (
        response.get("body", "") if isinstance(response, dict) else str(response))
    raw = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:6000]

    prompt = (
        "You are a strict freelance work reviewer. Decide whether the submitted work "
        "satisfies the client's rules.\n\n"
        f"CLIENT RULES:\n{rules}\n\n"
        f"SUBMITTED WORK:\n{text}\n\n"
        "Respond with ONLY a valid JSON object in this exact format:\n"
        '{"verdict": "True"} or {"verdict": "False"}\n\n'
        'Use "True" if the work satisfies the rules, "False" if it does not.\n'
        "Do NOT include any text outside the JSON object."
    )
    answer = gl.nondet.exec_prompt(prompt).strip()
    answer = re.sub(r"```json\s*", "", answer, flags=re.IGNORECASE)
    answer = re.sub(r"```\s*", "", answer)
    match = re.search(r"\{.*\}", answer, flags=re.DOTALL)
    if match:
        answer = match.group()
    try:
        data = json.loads(answer)
        v = str(data.get("verdict", "")).strip().lower()
        if v in ("true", "false"):
            return {"verdict": "True" if v == "true" else "False"}
    except (json.JSONDecodeError, KeyError):
        pass
    upper = answer.upper()
    if "FALSE" in upper and "TRUE" not in upper:
        return {"verdict": "False"}
    if "TRUE" in upper and "FALSE" not in upper:
        return {"verdict": "True"}
    return {"verdict": "False"}


class FreelanceArbitration(gl.Contract):
    client: str
    freelancer: str
    amount: u256
    rules: str
    work_link: str
    work_submitted: bool
    is_resolved: bool
    verdict: str

    def __init__(self):
        self.client = ""
        self.freelancer = ""
        self.amount = u256(0)
        self.rules = ""
        self.work_link = ""
        self.work_submitted = False
        self.is_resolved = False
        self.verdict = ""

    def _now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    @gl.public.write
    def create_job(self, rules: str, amount: u256) -> None:
        if self.client != "":
            raise gl.vm.UserError("Job already created")
        if not rules.strip():
            raise gl.vm.UserError("rules required")
        if amount == u256(0):
            raise gl.vm.UserError("amount must be positive")
        self.client = str(gl.message.sender_address)
        self.rules = rules
        self.amount = amount

    @gl.public.write
    def submit_work(self, work_link: str) -> str:
        if self.client == "":
            raise gl.vm.UserError("Job not created")
        if self.is_resolved:
            raise gl.vm.UserError("Job already resolved")
        if not work_link.startswith(("http://", "https://")):
            raise gl.vm.UserError("work_link must be http(s)")

        self.freelancer = str(gl.message.sender_address)
        self.work_link = work_link
        self.work_submitted = True

        # Capture into locals BEFORE the closures — the sandbox cannot read
        # contract storage inside a nondet block.
        target_url = work_link
        target_rules = self.rules

        def leader_fn() -> dict:
            return _review(target_url, target_rules)

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            mine = _review(target_url, target_rules)
            return mine.get("verdict") == leader_res.calldata.get("verdict")

        result = gl.vm.run_nondet(leader_fn, validator_fn)
        result_data = result.calldata if hasattr(result, "calldata") else result
        verdict = str(result_data.get("verdict", "False"))
        if verdict not in ("True", "False"):
            raise gl.vm.UserError("Consensus produced an invalid verdict")

        self.is_resolved = True
        self.verdict = verdict
        return verdict

    @gl.public.write
    def acknowledge_settlement(self) -> str:
        """Record that the arbitration decision has been settled off-chain.

        Marks the obligation discharged without moving value — the network
        cannot settle transfers, and claiming otherwise would be false.
        """
        if not self.is_resolved:
            raise gl.vm.UserError("Not resolved yet")
        if self.amount == u256(0):
            raise gl.vm.UserError("Already acknowledged")
        amount = int(self.amount)
        self.amount = u256(0)
        if self.verdict == "True":
            return f"SETTLED: {amount} wei owed to freelancer {self.freelancer}"
        return f"SETTLED: {amount} wei refunded to client {self.client}"

    @gl.public.view
    def get_job(self) -> dict:
        return {
            "client": self.client,
            "freelancer": self.freelancer,
            "amount": int(self.amount),
            "rules": self.rules,
            "work_link": self.work_link,
            "work_submitted": self.work_submitted,
            "is_resolved": self.is_resolved,
            "verdict": self.verdict,
        }

    @gl.public.view
    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
