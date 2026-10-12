# Freelance Arbitration Contract

A GenLayer Intelligent Contract where AI validators independently arbitrate
freelance work against plain-language rules and record a binding on-chain
decision.

**Deployed on Bradbury (chain 4221):** `0xDDB0591d336a25008582A64Ecf5ae45dc9AEbB9e`
**Explorer:** https://explorer-bradbury.genlayer.com/address/0xDDB0591d336a25008582A64Ecf5ae45dc9AEbB9e

---

## What it does

1. `create_job(rules, amount)` — the client defines plain-language rules and
   records the escrow amount owed on completion.
2. `submit_work(work_link)` — the freelancer submits a link to their completed
   work. AI validators independently review it against the rules and reach
   consensus on a verdict: **True** (work satisfies the rules) or **False**.
3. `acknowledge_settlement()` — records that the arbitration decision has been
   discharged.
4. `get_job()` — reads the full record: parties, escrow amount, rules, work
   link, verdict.

## How consensus is used

Each arbitration runs `gl.vm.run_nondet(leader_fn, validator_fn)`:

```python
def leader_fn() -> dict:
    return _review(target_url, target_rules)

def validator_fn(leader_res) -> bool:
    if not isinstance(leader_res, gl.vm.Return):
        return False
    mine = _review(target_url, target_rules)   # validator INDEPENDENTLY re-reviews
    return mine.get("verdict") == leader_res.calldata.get("verdict")
```

The leader fetches the work and judges it against the rules; **each validator
independently fetches the same work and reaches its own verdict**, agreeing only
if it reproduces the leader's verdict. The review logic lives in a module-level
function (`_review`) so leader and validators execute the identical code path,
and the LLM is prompted to emit exactly `{"verdict": "True"}` or
`{"verdict": "False"}` so the comparison is plain string equality with no fuzzy
scoring.

This deliberately does **not** use `gl.eq_principle.strict_eq` over an LLM
output: `strict_eq` does not enforce cross-validator equality for
non-deterministic LLM results (verified on-chain — a value that changes every
execution committed under `AGREE`), so a fabricated leader verdict would pass
unchecked.

## State model

`client`, `freelancer`, `amount` (u256), `rules`, `work_link`,
`work_submitted`, `is_resolved`, `verdict` — declared as class-level typed
fields, initialised in `__init__`.

## Verification (on-chain, read back from Bradbury)

**Positive case** — work that satisfies the rule "must mention hello world":

| Step | Result |
|---|---|
| `create_job` | AGREE — escrow 1,000,000,000,000,000 wei recorded |
| `submit_work` | AGREE, `FINISHED_WITH_RETURN` |
| committed verdict | **True** |
| `acknowledge_settlement` | AGREE — obligation discharged |

**Adversarial case** — a rigged leader fabricated `True` on work that fails the
stated rule:

| Round | Result |
|---|---|
| #1–#6 | **DISAGREE** (every round) |
| committed state | **none** |

The validators independently judged the work, saw it differ from the fabricated
verdict, and refused to commit.

## Value settlement — stated plainly

The value-moving primitives (`gl.pay`, `emit_transfer`) **do not settle on this
network**. Verified on-chain: a minimal payable contract that immediately pays
`gl.message.value` back to the sender returned `FINISHED_WITH_ERROR` with zero
executions, and `emit_transfer` reverted on the consensus contract.

The contract therefore does not claim a working payout path. The escrow is
recorded as a durable, consensus-derived **obligation**, and the arbitration
**decision** is the binding on-chain artifact; actual settlement happens
off-chain against that decision. This limitation is documented rather than
disguised.

## Contract layout

- `contracts/freelance_arbitration.py` — the contract (Bradbury pattern:
  `from genlayer import *`, `gl.Contract`, `@allow_storage`-free scalar storage,
  `gl.vm.run_nondet`)

## Deploy

```bash
# Bradbury (chain 4221), genlayer-js, code passed as a UTF-8 string
DEPLOY_PK=0x<key> node deploy.mjs
```
