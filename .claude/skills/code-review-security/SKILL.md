---
name: code-review-security
description: Reviews code for security vulnerabilities and user-impacting functional bugs (race conditions, double charges, swallowed errors, data loss, broken authorization) and reports findings with concrete scenarios and fix code. Use for code reviews, "any vulnerabilities/bugs?", "is this production-ready?", and to self-check Python/SQL/Supabase code before delivering it.
---

# Code Review: Security + Functional Correctness

The goal is to find **every way this code can hurt its users**. Two kinds of harm matter equally:

1. **Security harm:** unauthorized access, data leaks, injection, exposed secrets.
2. **Functional harm:** the code looks like it works but produces wrong results. A customer gets charged twice, data silently disappears, a balance goes negative, an error is swallowed and nobody notices.

Most reviews only look for the first kind. In practice, users get burned most often by the second, because those are business-logic bugs that linters and SAST tools cannot catch. Treat both axes with the same seriousness.

## Two modes

**A) Review mode:** the user asks you to review code. Run the full process below and write a report. Don't modify the user's code; propose fixes. Only apply fixes if the user explicitly asks.

**B) Self-check mode:** you just wrote or changed Python / SQL / Supabase code. Before delivering, run the checklists below against your own code and **fix what you find directly**. End your answer with a short **"Security / correctness notes"** section of 2–5 bullets: what you guarded against, and the remaining risks the user should know about (e.g. "refunds don't claw back credits", "no rate limiting"). Don't write a long report.

Never claim you tested code you did not actually run. If you did test it, include the test file with your outputs. An unverified "tested" claim gives the user false confidence.

## Review process

### 1. Understand the intent
Who is this code for, what data does it handle, when is it called? The only way to find functional bugs is to know what the code is *supposed* to do. If the intent is unclear, make a reasonable assumption and state it in the report.

### 2. Map trust boundaries and data flow
- Mark every externally controlled input: HTTP params, body, headers, cookies, files, webhooks, user-written data read back from the DB.
- Trace where each input flows: SQL, shell, file paths, HTML, outbound requests, logs.
- Is identity/authorization verified **server-side**, or does the code trust a `user_id` / `role` / `price` field sent by the client?

### 3. Walk the checklists
Go through the sections below that apply: Python, Supabase/SQL, and always Functional correctness.

### 4. Verify every finding
Before reporting, ask: **"Can I write a concrete input or situation that triggers this?"** If not, it's either not a finding or it belongs under "Possible / needs verification". False positives distract from real problems. If the framework already protects against it (parameterized queries, template auto-escaping), don't report it. Merge symptoms with the same root cause into one finding.

### 5. Assign severity

| Severity | Meaning |
|---|---|
| 🔴 **Critical** | Easily exploitable or direct money/data loss: SQL injection, access to other users' data, table without RLS, double charge |
| 🟠 **High** | Serious harm but requires a condition: race condition, swallowed payment error, weak token |
| 🟡 **Medium** | Limited impact / missing defense layer: no rate limit, internal details in error messages |
| 🔵 **Low** | Best-practice gap |

Base severity on the **realistic worst outcome** and **how easy it is to trigger**.

## Report format (review mode)

Write in the user's language (Turkish question → Turkish report). Be concise: a few lines per finding plus fix code.

```markdown
## Summary
[1–3 sentences: what the code does, overall state, biggest risk. Finding count by severity.]

## Findings

### 🔴 [Short title] — `file.py:line`
**Type:** Security | Functional
**Problem:** [1–2 sentences]
**Scenario:** [Concrete trigger: "User A sends `order_id=42`; order 42 belongs to user B; there is no ownership check, so B's address is returned."]
**Impact:** [Real harm to users / the business]
**Fix:**
(code block showing only the changed part)

[...remaining findings in severity order...]

## Possible / needs verification
[Risks that depend on code or config you can't see: "If RLS is off on the orders table, this is critical."]

## Before going live
[Only if the user mentioned shipping / production: a prioritized to-do list of 3–7 items.]

## Done well
[1–3 bullets, if any.]
```

- **Every Critical and High finding must include fix code.** Saying "use a transaction" isn't enough; show how. Match the original code's style and libraries.
- Don't invent findings. "No critical/high findings" is a valid result; in that case briefly list the categories you checked.
- For large codebases, focus on the riskiest paths (auth, payments, deletion, endpoints handling external input) and state your scope.

---

# Checklist: Python

**Injection**
- SQL built with f-strings / `%` / `.format()` / `+`: `cur.execute(f"... '{email}'")` is bad, `cur.execute("... %s", (email,))` is good. Same risk with SQLAlchemy `text(f"...")` and Django `.raw()/.extra()`.
- Table/column names can't be parameterized. Use an **allowlist** for things like `ORDER BY {sort}`.
- Commands: `os.system`, `subprocess(..., shell=True)` with input. Use list-argument `subprocess.run([...])`.
- Templates: `render_template_string(user_input)` (SSTI), `Markup()` / `|safe` on user data (XSS).
- Path traversal: `os.path.join(BASE, filename)` discards BASE when given an absolute path. Use `Path(...).resolve()` + `is_relative_to(base)`. Watch for zip slip when extracting archives.
- `pickle.loads`, unsafe `yaml.load`, `eval/exec` on untrusted data lead to remote code execution.

**Authorization**
- **IDOR:** every endpoint that fetches a resource by ID must check `resource.user_id == current_user.id`. This is the most common critical finding.
- Never trust client-sent `user_id`, `is_admin`, `role`, `price`. Identity comes from the token, prices from the DB.
- Mass assignment: with `User(**request.json)` a user can send `is_admin=True`. Use explicit field lists in Pydantic schemas.
- Routers missing the auth dependency/decorator, JWT with `verify_signature: False` or no `algorithms`, `@csrf_exempt`, `allow_origins=["*"]` with credentials.

**Secrets and crypto**
- Hardcoded keys, `DEBUG=True`, logging passwords/tokens/full request bodies, returning `str(e)` / tracebacks to clients.
- Use `secrets`, not `random`, for tokens/OTPs. Use bcrypt/argon2, not md5/sha, for passwords. Use `hmac.compare_digest`, not `==`, to compare signatures/tokens.
- Webhook signature not verified, or verified against parsed JSON instead of the raw body.

**Network / files**
- SSRF: `requests.get` on a user-supplied URL (internal network, `169.254.169.254`). Missing `timeout`, `verify=False`.
- File uploads without type/size limits. Open redirect: `redirect(request.args["next"])`.

**Python-specific functional traps**
- Mutable default argument (`def f(x, items=[])`): the list is shared across calls, even across users.
- `float` for money: use `Decimal("0.10")` or integer cents. `round(2.5) == 2` (banker's rounding).
- **Numeric input validation:** negative, zero, `NaN`, `inf`. Every comparison with `float("nan")` is `False`, so it slips past `if amount > balance`. `float("-inf")` / `"Infinity"` can arrive via JSON. Use Pydantic `Field(gt=0, allow_inf_nan=False)` or `Decimal` + `is_finite()`.
- Truthiness: `if not amount:` rejects a valid `0`; use `is None` for None checks.
- `except Exception: pass` or returning `None` on error swallows failures. Bare `except:` even catches Ctrl-C.
- Naive datetimes (`datetime.now()`, `utcnow()`): use `datetime.now(timezone.utc)`.
- Never use `assert` for security checks; `python -O` strips them.
- Cap `offset/limit` when they come from the user.
- Blocking calls (sync `requests`, sync Supabase client) inside async functions stall the whole event loop. An un-awaited coroutine never runs.

---

# Checklist: SQL / Postgres / Supabase

In Supabase the client talks to the database **directly**, and the `anon` key is public. For every table, ask: **"What can anyone holding the anon key do to this table?"**

**Row Level Security**
- Does every table in `public` have `ENABLE ROW LEVEL SECURITY`? With RLS off, the whole table is readable and writable: 🔴.
- RLS on but no policies means nobody can access it. That's a functional bug: the app silently sees empty lists.
- Overly broad policies: `USING (true)`, writes allowed to `anon`, `auth.role() = 'authenticated'` (every logged-in user sees everyone's rows).
- `INSERT` policy without `WITH CHECK`, or `WITH CHECK (true)`: users can insert rows on behalf of others.
- `UPDATE` policy without `WITH CHECK` / column restrictions: users can change `role`, `balance`, `is_admin` on their own row. Use column-level `GRANT UPDATE (...)` or a trigger.
- Don't check roles via `auth.jwt() -> 'user_metadata'`: **users can edit their own user_metadata**. Use `app_metadata` or a separate table.
- Views bypass RLS. Use `WITH (security_invoker = true)`.

**Keys**
- `service_role` key visible client-side (`NEXT_PUBLIC_`, `VITE_`, mobile app, repo): 🔴.
- A backend using `service_role` has no RLS, so the code itself must enforce ownership. `service_role` + a `user_id` taken from the request = IDOR.

**Functions (RPC)**
- `SECURITY DEFINER` bypasses RLS. Is ownership checked inside with `auth.uid()`? Don't accept a `user_id` parameter and trust it.
- Without `SET search_path = ''`, the search_path can be hijacked. Schema-qualify tables (`public.x`).
- Functions in `public` are callable by `anon` via `/rpc/` by default. `REVOKE EXECUTE ... FROM public, anon, authenticated` when needed.
- `CREATE OR REPLACE` with a changed signature does not remove the old function. The old vulnerable version needs an explicit `DROP FUNCTION`.
- Dynamic SQL: use `format('%I %L')` or `USING`, not `EXECUTE '...' || p`.
- A function that silently returns `void` on failure makes the client think it succeeded. Use `RAISE EXCEPTION`.

**Edge Functions / Storage / Auth**
- With `verify_jwt = false`, is signature/identity verification done in code? Is `res.ok` checked on external API calls?
- A bucket holding personal documents with `public: true` exposes every file. Do `storage.objects` policies tie folders to the user (`(storage.foldername(name))[1] = auth.uid()::text`)?
- Is there a signup trigger creating profile/wallet rows, and what happens if it fails? What happens to related data when a user is deleted?

**Filter injection**
- String interpolation in supabase-py / js filters like `.or_(f"name.eq.{q}")` allows PostgREST filter injection. Same for `.order(user_input)`, `.select(user_input)`.

**Schema and migrations**
- Missing `UNIQUE` (email, `payment_intent_id`, `(user_id, coupon_id)`) leads to duplicates. Missing `NOT NULL`, `CHECK (balance >= 0)`, `CHECK (amount > 0)`.
- Money in `double precision`: use `numeric(12,2)` or integer cents. Float columns also accept `'Infinity'` / `'NaN'`.
- Use `timestamptz`, not `timestamp`.
- `ON DELETE CASCADE` can wipe invoices/transaction history. Missing foreign keys leave orphan rows.
- Migrations: `DROP` without backup, data-truncating `ALTER TYPE`, index without `CONCURRENTLY`, forgetting RLS on new tables, adding a `NOT NULL` column without a default.

**Concurrency**
- Read → compute in app → write is racy. Instead:
  ```sql
  UPDATE wallets SET balance = balance - $2
  WHERE id = $1 AND balance >= $2
  RETURNING balance;  -- 0 rows = insufficient balance
  ```
  Or `SELECT ... FOR UPDATE` inside a transaction. When locking two rows, lock in a fixed order to avoid deadlocks.
- The Supabase client has no transactions. Move multi-write operations into a single PL/pgSQL function (RPC).
- After `ON CONFLICT DO NOTHING`, does the code assume the row was inserted? Checking a limit with `COUNT(*)` and then inserting is racy.

---

# Checklist: Functional correctness (any language)

For every function, ask: **"In what situation does this code do the wrong thing to a user without anyone noticing?"**

- **Races (TOCTOU):** in "is the coupon used? → no → use it", two concurrent requests both see "no". Same for stock, balance, usernames, free trials. Scenario: double click, two tabs. Fix: UNIQUE constraint, atomic conditional UPDATE, locking.
- **Idempotency:** webhooks are delivered at least once. Is the event/session ID recorded and duplicates rejected? Do retries, queues, or client retries after timeouts produce duplicate records, emails, or charges?
- **Partial failure:** if step 2 fails, what state does step 1 leave behind? Money taken but no order; order shows "paid" but payment failed; file uploaded but no DB row. Fix: transactions, side effects after commit, a `pending → paid` status field.
- **Error handling:** swallowed exceptions, `200` / `success: true` on failure, unchecked status codes from external services. **Fail-open:** if the auth service errors, access must be denied. `return` inside `finally` swallows exceptions.
- **Edge cases:** empty list, `None`, `0`, negative, `NaN/Infinity`, huge values, Unicode, whitespace, case (`Ali@x.com` vs `ali@x.com` creates two accounts). Unchecked `[0]` / `.first()`, division by zero, off-by-one. Non-deterministic `ORDER BY` skips rows across pages.
- **Money, numbers, time:** where is rounding done (per line or on total)? Discount/tax order? Discount over 100% gives a negative price. Mixed currencies. Time zones ("today" in UTC or the user's zone?), month end, DST, `<` vs `<=` on expiry checks.
- **Business rules:** invalid state transitions (can a cancelled order be shipped?). Rules enforced client-side but not server-side (price, stock, limits). With soft delete, does every query filter deleted rows?
- **External services:** no timeout, unbounded retries, 429 not handled, `KeyError` → 500 when a response field is missing.
- **Silent data loss:** lost updates (two people save the same record, the first change is lost). `UPDATE/DELETE` hitting all rows when a filter value is `None`. Records silently skipped in batch jobs. Missing encoding breaks non-ASCII characters.
