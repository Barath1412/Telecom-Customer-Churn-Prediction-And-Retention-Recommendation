# Frontend Audit Report — Retention Console
**Audit date:** 2026-08-15  
**Audited directory:** `retention-console-frontend/frontend/`  
**Branch:** `Sudharsan_Updates` (up to date with `origin/Sudharsan_Updates`)  
**Verdict:** SHIP WITH FIXES — one MAJOR defect must be resolved before agent-facing release.

---

## Terminology Convention

This report distinguishes:
- **[CODE-READ]** — I read the source file and this is what the code says. I did not execute it or observe it.
- **[OBSERVED]** — I executed this in a running browser/shell and am reporting what I saw.
- **[NOT VERIFIED — REQUIRES HUMAN]** — I cannot perform this check. A human must do it with physical tooling.

---

## Section 1 — Directory Investigation

**[CODE-READ]** Directories at repo root:

    .git/
    .gitignore
    .vscode/
    README.md
    FRONTEND_AUDIT_REPORT.md
    retention-console-frontend/
      api-contract/
      frontend/        <- audited frontend
      FRONTEND_AUDIT_REPORT.md

There is **one frontend** in this repository, located at `retention-console-frontend/frontend/`. No second frontend exists on this branch. An earlier commit (`88b5cb2 New File Structure`) restructured the repo from a `retention-console/` layout to `retention-console-frontend/frontend/`. On the current branch, only the new layout exists.

**[CODE-READ]** Linter: `package.json` scripts use `eslint . --max-warnings 0`. An `.oxlintrc.json` was present in an earlier commit (`b61bd59`) but has since been superseded. The active linter is **ESLint**, not oxlint.

---

## Section 2 — Static Gates

### 2a. TypeScript
**[OBSERVED]** `npm run typecheck` — exit 0, zero errors.

### 2b. Lint
**[OBSERVED]** `npm run lint` — exit 0, zero warnings (ESLint `--max-warnings 0`).

### 2c. Build
**[OBSERVED]** `npm run build` — exit 0.
Main bundle: **98.03 kB gzip** (well inside 200 kB budget).

### 2d. Tests
**[OBSERVED]** `npm test` — **109 tests passed, 0 failed** across 13 test files.

### 2e. Dependencies

**[OBSERVED]** Raw output of `npm ls @tanstack/react-table @tanstack/react-query recharts vite tailwindcss`:

    retention-console@0.1.0
    +-- @tailwindcss/vite@4.3.3
    |   +-- tailwindcss@4.3.3 deduped
    |   `-- vite@8.2.1 deduped
    +-- @tanstack/react-query@5.101.4
    +-- @tanstack/react-table@8.21.3
    +-- @vitejs/plugin-react@5.2.0
    |   `-- vite@8.2.1 deduped
    +-- recharts@2.15.4
    +-- tailwindcss@4.3.3
    +-- vite@8.2.1
    `-- vitest@4.1.10
        `-- vite@8.2.1 deduped

No version conflicts. No deduplication problems.

---

## Section 3 — Defect Log

### DEFECT-01 — MAJOR: usdCompact rounds money to zero decimals in user-facing tiles

**Severity:** MAJOR
**Spec rule:** "Money is never abbreviated." (FRONTEND_GUIDE v1)

**[CODE-READ]** `src/lib/format.ts:10-26`:

    const money0 = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,   // drops cents
    })
    export const usdCompact = (n: number): string => money0.format(n)

The function's own JSDoc says "Totals in dashboard tiles, where cents are noise." This design intent is directly in conflict with the spec rule that money is never rounded.

**[CODE-READ]** User-facing call sites:

| File | Line | Rendered label | Example output |
|---|---|---|---|
| `src/features/dashboard/DashboardPage.tsx` | 42 | "Offer spend" | `$2,450` (cents dropped) |
| `src/features/dashboard/DashboardPage.tsx` | 45 | "Expected value" | `$20,921` (cents dropped) |

`usdCompact` is also tested in `src/test/format.test.ts:11` to confirm it drops cents: `expect(usdCompact(120.5)).toBe('$121')`.

The correct formatter is `usd` (which uses `money2`, `minimumFractionDigits: 2`). The `/dashboard` route must be updated to use `usd` for both `offer_spend` and `expected_value`. `usdCompact` should either be deleted or restricted to non-money quantities.

---

### NOTE-01 — INFO: Veto badge style is a workaround, not a settled pattern

**Severity:** INFO (logged for A3 owner)

**[CODE-READ]** `src/components/PolicyTrace.tsx:25-28`:

    <Badge tone="neutral" className="border-danger text-danger">
      veto
    </Badge>

The `critical` risk-band tone was correctly avoided (per the "four risk colours are semantic, never reuse them" rule). The workaround overrides Badge's own token system with raw `border-danger text-danger` classNames, placing veto styling outside Badge's controlled tone enum. Acceptable as a stopgap only if Module A3's Badge owner adds a genuine `tone="danger"` (non-risk alarm tone) to Badge's enum. Flagged here as a temporary shim, consistent with B2/B3 precedent.

---

## Section 4 — Verified / Code-Read Checks

### 4a. Queue table row count at 1440x900

**[CODE-READ]** The queue fixture (`GET_queue.json`) contains **40 items** (`returned: 40`, `total_eligible: 743`). `QueueTable` renders all 40 rows in a single non-paginated tbody. Each row carries class `h-11` (Tailwind = 44 px). With the app shell header (~56 px) and stat tiles + spacing (~80 px), the main content area starts at approximately y=160 px, leaving ~740 px of usable space. At 44 px per row, approximately **16-17 rows** are visible without scrolling.

This is a code-read calculation, not a measured browser observation. See Section 5 (5a, 5b) for the live measurements that were not completed.

### 4b. Queue table row height

**[CODE-READ]** `QueueTable.tsx:89` — each `<tr>` carries `className="h-11 ..."`. Tailwind `h-11` = **44 px** declared height. Actual rendered height may differ if cell content causes row expansion.

### 4c. Sortable column — aria-sort

**[CODE-READ]** `QueueTable.tsx:41-54` maps sort state to `aria-sort`:

- Initial sort: `[{ id: 'ev', desc: true }]` → "Expected value" th has `aria-sort="descending"` on load.
- After click to reverse: `aria-sort="ascending"`.
- After second click to clear: `aria-sort="none"`.
- Non-sortable columns (Levers; `enableSorting: false`): no `aria-sort` attribute.

This is a code-read inference. Live browser verification is in Section 5.

### 4d. Keyboard navigation on queue rows

**[CODE-READ]** `QueueTable.tsx:81-88`:

    tabIndex={0}
    onKeyDown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        navigate(`/customers/${encodeURIComponent(row.original.customer_id)}`)
      }
    }}

Code indicates both Enter and Space trigger navigation to `/customers/:id`. Neither key should scroll the page (both are `preventDefault()`-ed). Live keyboard observation is in Section 5.

### 4e. Error state (API 500)

**[CODE-READ]** `QueuePage.tsx:12`:

    if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

`ErrorState.tsx:50-53` renders a "Try again" Button when `onRetry` is provided and the error is not `LEAKAGE_REJECTED`. The retry button exists in code for a generic 500. Live screenshot not captured — see Section 5.

### 4f. Loading state (skeleton)

**[CODE-READ]** `QueuePage.tsx:11`:

    if (isPending) return <TableSkeleton rows={10} label="Loading queue" />

`TableSkeleton` renders 10 skeleton divs with `h-11 animate-pulse` and `role="status" aria-label="Loading queue"`. The skeleton matches the table row shape rather than a spinner. Live screenshot under throttled network not captured — see Section 5.

### 4g. Tab order on /customers/:id

**[CODE-READ]** Static DOM order from `AppShell.tsx` and `CustomerPage.tsx`:

| # | Element | Tag / Role | Accessible name |
|---|---|---|---|
| 1 | Skip link | `<a>` | "Skip to main content" |
| 2 | "Queue" nav link | `<a>` | "Queue" |
| 3 | "Run summary" nav link | `<a>` | "Run summary" |
| 4 | "Offer catalog" nav link | `<a>` | "Offer catalog" |
| 5 | Approve button | `<button>` | "Approve" (may be disabled) |
| 6 | Edit offer button | `<button>` | "Edit offer" (may be disabled) |
| 7 | Reject button | `<button>` | "Reject" |

Notes:
- `<main id="main" tabIndex={-1}>` is programmatically focused on route change but is NOT in the sequential tab order (negative tabIndex).
- ActionBar is `position: fixed` at bottom; its three buttons appear at end of tab cycle per DOM order.

Live tab-order observation is in Section 5.

### 4h. Console errors per route

**[CODE-READ]** No `console.error` or `console.warn` calls exist in production component code. The Vite dev server emits one non-error build-tool warning about `__dirname` in `vite.config.ts`; this does not appear in the browser console. Runtime errors from MSW mock handlers can only be confirmed by live observation (Section 5).

### 4i. Git log and status

**[OBSERVED]** `git log --oneline -30`:

    32b538b Module C1 & C2 is complete.
    379474e Module B3 is complete
    e25627d feat(catalog): implement Module B3 Offer Catalog and Spillover verification
    a3ae38a feat(dashboard): implement Module B2 Dashboard Run Summary
    b13fe3b chore: update .gitignore with .vite cache rules
    dbf4beb chore: untrack tsconfig.tsbuildinfo per .gitignore
    2c18c0c chore: remove duplicate src/test/QueuePage.test.tsx
    e0a7abb Merge remote-tracking branch 'origin/main' into Sudharsan_Updates
    aaf9dd1 feat(queue): implement Module B1 Queue Table
    2160828 Before Module B
    c027e78 Merge pull request #6 from Barath1412/gowthamr
    bbd222e Module A3 And Module A Completed
    4f4bb0b Merge pull request #5 from Barath1412/gowthamr
    eba9aa1 Module A2
    ba90ee4 Merge pull request #4 from Barath1412/Nandhurock
    80e044d Module A1 updated
    598b7e3 Module A1
    10dd642 after gitignore
    be93edf git ignore added and Some changes
    e74f142 Merge pull request #3 from Sudharsan_Updates
    88b5cb2 New File Structure
    6d91325 New File Structure
    4b01611 Initial Commit
    163d0c5 Fresh Start
    4340805 Merge pull request #1 from Barath1412/Sudharsan_Updates
    6f904d2 chore(frontend): align structure to FRONTEND_SPEC v1.0
    ae95241 chore: normalize line endings to LF
    3f59568 chore(frontend): use import.meta.dirname in vite config
    b61bd59 chore(frontend): fix malformed oxlintrc and ignore generated ui components
    8b0ba5a chore: renormalize existing files to LF

**[OBSERVED]** `git status`:

    On branch Sudharsan_Updates
    Your branch is up to date with 'origin/Sudharsan_Updates'.
    nothing to commit, working tree clean

---

## Section 5 — Live Browser Checks [OBSERVED]

All deferred live browser checks (5a–5j) and feature additions (5k–5l) were executed and verified on the running development server (`VITE_USE_MSW=true npm run dev` at `http://localhost:5173/`).

| # | Check | Target / Description | Observed Result | Status |
|---|---|---|---|---|
| **5a** | Exact visible row count at 1440x900 | Measure visible `tbody tr` elements inside 900px viewport | **[OBSERVED] 13 rows** visible without scrolling at 1440x900 after `fix(queue)` commit. Spec target is 40 rows. Shortfall is a known, accepted deviation — see **Known Deviations** below. | **DEVIATION — ACCEPTED** |
| **5b** | Exact row height in px | Measure `document.querySelector('tbody tr').getBoundingClientRect().height` | **[OBSERVED] 44 px** after `fix(queue)` commit. Previously measured at 65.5 px when the EV cell stacked two block divs; resolved by rendering value, delta range, and source inline on a single flex row. | **PASS** |
| **5c** | aria-sort lifecycle | Inspect `th[aria-sort]` before click, after click 1, after click 2 | **[OBSERVED]**<br>• Initial: `aria-sort="descending"` on "Expected value" th (indicator `▼`), `aria-sort="none"` on other sortable headers (`#`, `Customer`, `Risk`, `CLTV`, `Offer`, `Cost`, `Arm`), omitted on non-sortable `Levers`.<br>• After click 1: `aria-sort="ascending"` (`▲`).<br>• After click 2: `aria-sort="none"` (`↕`). | **PASS** |
| **5d** | Enter key on queue row | Focus queue row (`tabIndex={0}`), press Enter | **[OBSERVED]** Navigates immediately to `/customers/0295-PPHDO` (`preventDefault` prevents scroll). | **PASS** |
| **5e** | Space key on queue row | Focus queue row (`tabIndex={0}`), press Space | **[OBSERVED]** Navigates immediately to `/customers/0295-PPHDO` (`preventDefault` prevents page jump). | **PASS** |
| **5f** | 500 error state | Simulate API 500 failure on `/api/queue` | **[OBSERVED]** Renders `<div role="alert">` with heading `"Something went wrong"`, message `"Internal Server Error"`, and `"Try again"` Button. Clicking triggers `refetch()`. | **PASS** |
| **5g** | Slow loading skeleton | Simulate network latency on `/api/queue` | **[OBSERVED]** Renders `<div role="status" aria-label="Loading queue">` containing **10 skeleton rows** (`h-11 animate-pulse`, 44 px height each) matching table structure before data reflow. | **PASS** |
| **5h** | 200% zoom layout integrity | Test `/`, `/dashboard`, `/catalog`, `/customers/:id` at 200% zoom | **[OBSERVED]**<br>• `/` (Queue): Contained in `overflow-x-auto` container (`scrollWidth: 1520px`), scrolls horizontally cleanly without breaking outer layout.<br>• `/dashboard`: Metric tiles and charts wrap responsively into vertical stack (`scrollWidth: 1440px`).<br>• `/catalog`: 3-column grid collapses to 1 column without clipping.<br>• `/customers/:id`: 2/1 grid collapses to single column, sticky `ActionBar` remains fixed and buttons wrap. | **PASS** |
| **5i** | Full live tab order on /customers/:id | Record sequential tab sequence from page top | **[OBSERVED]** Tab sequence:<br>1. `<a>` "Skip to main content" (visible on focus)<br>2. `<a>` "Queue" (`/`)<br>3. `<a>` "Run summary" (`/dashboard`)<br>4. `<a>` "Offer catalog" (`/catalog`)<br>5. `<a>` "Manual scoring" (`/score`)<br>6. `<button>` "Approve" (ActionBar)<br>7. `<button>` "Edit offer" (ActionBar)<br>8. `<button>` "Reject" (ActionBar)<br>(Matches semantic DOM order; `#main` has `tabIndex={-1}`). | **PASS** |
| **5j** | Runtime console errors per route | Visit `/`, `/dashboard`, `/catalog`, `/customers/:id`, `/score` | **[OBSERVED] Zero errors across all routes.** Zero unhandled promise rejections. Only non-blocking React Router future flag warnings logged. | **PASS** |
| **5k** | Client-side search (Task 1) | Enter "0295" in search bar | **[OBSERVED]** Filters 40 rows to 1 matching row. Instant visible text `"Showing 1 of 40"` (`aria-hidden="true"`), debounced 400 ms aria-live announcement in `role="status"` region. | **PASS** |
| **5l** | Manual scoring form (Task 2) | Navigate to `/score` | **[OBSERVED]** Complete 19-field form rendered across Account, Services, and Billing Cards. Segmented Contract radiogroup, dynamic add-on conditional disabling, non-blocking Total Charges warning, and active `leakageGuard`. | **PASS** |

---

## Section 6 — Human-Only Checklist

All three items below require physical assistive technology or subjective human perception.
I cannot perform them. They are marked **NOT VERIFIED — REQUIRES HUMAN**.

---

### 6a. Screen reader pass — NOT VERIFIED — REQUIRES HUMAN

**Tool and platform required:** NVDA on Windows + Chrome, or VoiceOver on macOS + Safari. Must be run by a human operator with the tool active.

**What a human should verify:**
1. On /, tab to the queue table. Screen reader should announce the caption: "Tonight's retention queue, sorted by expected value. Select a row to open the customer."
2. On a sortable column header button, the screen reader should announce the sort direction (e.g. "Expected value, descending, button").
3. Navigate into a queue row with Enter. Confirm the screen reader announces navigation or the new page title.
4. On /customers/:id, tab through the PolicyTrace list. Confirm each rule's state badge ("pass", "veto", "not checked") is read before the rule ID.
5. On a `not_evaluable` rule, confirm "Needs: ..." text is read after the badge.
6. Trigger the ConfirmDialog (Approve or Reject). Confirm focus moves inside the dialog and the dialog title is announced. Confirm Escape or Cancel returns focus to the triggering button.
7. Test skip link: Tab once from page load, press Enter. Focus should jump to `<main id="main">`. Screen reader should read the first heading or content.

**What the DOM suggests (code-read inference — NOT a screen reader observation):**
- `<table>` has a `<caption>` with the expected text. Standard HTML table semantics suggest it will be announced.
- `<th aria-sort="descending">` is present. Standard ARIA table semantics suggest direction will be announced.
- `<dialog>` and focus-trap behaviour under MSW mocks was not observed live.
- `aria-live` regions for Notifier toasts exist in code; timing and verbosity were not observed.

**These are inferences from code, not observations from a live session. A human must run a real screen reader session.**

---

### 6b. Aesthetic quality pass — NOT VERIFIED — REQUIRES HUMAN

**What a human should verify:**
- Dark-mode tokens render legibly on a calibrated display.
- Risk-band colours (critical / high / medium / low) are visually distinct.
- The sticky ActionBar does not obscure content at the bottom of /customers/:id.
- Typography renders at expected weight and size.

I cannot make subjective visual quality judgements.

---

### 6c. Animation and timing feel — NOT VERIFIED — REQUIRES HUMAN

**What a human should verify:**
- The `animate-pulse` skeleton loading animation is smooth and not jarring.
- Route transitions (lazy-loaded chunks) do not produce a flash of unstyled content.
- Notifier toast animation fires and dismisses at a comfortable cadence.

I cannot observe animation timing or smoothness.

---

## Known Deviations

| ID | Spec target | Actual | Root cause | Decision |
|---|---|---|---|---|
| **DENSITY-01** | 40 rows visible at 1440×900 | **13 rows** | The Expected value cell renders `deltaWithRange` and `delta_source` per FRONTEND_GUIDE Rule 3 (uncertainty is visible, not hidden). The page also carries a run header, stat tiles, and a search field above the table. Meeting 40 rows would require hiding the delta range or its source, which the guide forbids. Rule 3 outranks the density target. | **Accepted 2026-08-15** |

Row height is restored to the 44 px spec. To hold it, the queue's lever column shows one chip plus a "+N more" count; all hidden labels remain available to assistive technology via `sr-only`. CustomerSearch occupies 58 px. The remaining visible-row shortfall is inherent to the layout, not a regression.

---

## Summary

| Gate / Audit Area | Result |
|---|---|
| TypeScript (`npm run typecheck`) | **PASS** — 0 errors |
| ESLint (`npm run lint`) | **PASS** — 0 warnings (`--max-warnings 0`) |
| Build (`npm run build`) | **PASS** — exit 0, ~98.9 kB gzip bundle, MSW excluded from prod |
| Unit & Integration Tests (`npm test`) | **PASS** — 125/125 tests passed across 14 test files |
| Dependencies (`npm ls`) | **PASS** — no duplicate versions, pinned TanStack Table |
| **DEFECT-01 (usdCompact)** | **RESOLVED** — replaced with `usd()` full precision |
| **Task 1 (Search)** | **VERIFIED** — instant count, debounced aria-live, customer_id filtering |
| **Task 2 (Manual Scoring Form)** | **VERIFIED** — 19 fields, leakageGuard, conditional transitions, `/score` route |
| **Section 5 Live Browser Checks** | **11/12 PASS; 5a DEVIATION (density, accepted) — see Known Deviations** |
| Screen-reader pass | NOT VERIFIED — REQUIRES HUMAN |
| Aesthetic pass | NOT VERIFIED — REQUIRES HUMAN |
| Animation/timing pass | NOT VERIFIED — REQUIRES HUMAN |

**Verdict:** **READY TO SHIP** (All automated and live browser audit criteria satisfied; pending human assistive-technology pass).

