# Marwick v0.7

Personal spending analysis prototype. It compares two periods, shows which categories drove the change, and links every figure to its transactions.

**Principle: calculate first, explain second.** All figures come from a deterministic, tested engine that uses integer cents. No AI model is used in v0.7.

---

## Install and run (Windows, VS Code)

1. Install **Python 3.11 or later** from python.org. During setup, tick **"Add python.exe to PATH"**.
2. Unzip `marwick_v0.7.zip` into a folder, for example `Documents\marwick_v0.7`.
3. In VS Code, choose **File → Open Folder…** and select that folder.
4. Open a terminal with **Terminal → New Terminal** (PowerShell), then run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   If PowerShell blocks the activation script, run this once and then activate again:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

5. Run the tests (about 10 seconds):

   ```powershell
   python -m pytest -q
   ```

   Expected result: `77 passed`.

6. Start the app:

   ```powershell
   python -m streamlit run app.py
   ```

   It opens at http://localhost:8501. Click **Try with sample data** to explore, or upload your own CSV.

To stop the app, press `Ctrl + C` in the terminal. Next time, you only need step 4's activate line, then step 6.

---

## Project structure

```
app.py                  Entry point: sidebar and page routing only
marwick/                Financial engine (no Streamlit; importable and testable)
  validators.py         CSV reading, amount/date parsing to integer cents, mapping guess, duplicates
  classify.py           Transaction Type + Spending Category rules, corrections, review flags
  engine.py             Period metrics, buckets, category table, % change rules, weekly series
  insights.py           Deterministic insights, each with its figures and evidence IDs
  pipeline.py           One call: CSV -> clean -> classify -> corrections -> review flags
  utils.py              Money formatting, stable transaction IDs, period presets
ui/                     Streamlit presentation
  theme.py              Colours, CSS, logo handling, HTML components, chart theme
  state.py              Session state and the per-run data bundle
  components.py         KPI cards, charts, tables, transaction editor, insight cards
  pages/                overview, analyse, transactions, insights, settings
tests/                  77 automated tests (engine, classification, validation, app smoke tests)
assets/                 Official Marwick logo files (used as supplied)
sample_data/            Fictional three-month export for demos and tests
.streamlit/config.toml  Theme and server settings
```

---

## Feature status

### Implemented and tested
- CSV upload with header or no-header; automatic column detection, adjustable by you
- One amount column (either sign convention) or separate debit and credit columns
- Amounts parsed exactly into integer cents (`$1,234.56`, `(12.50)`, `12.50 DR` and similar)
- Unreadable rows listed with a reason and excluded visibly, never silently
- Transaction Type (Expense, Income, Refund, Internal Transfer) kept separate from Spending Category
- Whole-word keyword rules; the longest match wins (`uber eats` beats `uber`)
- Refund wording only creates a Refund when money comes in
- Internal Transfer only when the transfer mentions one of your own account suffixes
- Review flags with reasons, shown in every table
- Manual corrections saved by stable transaction ID. They survive filtering, navigation and settings changes.
- Possible duplicates flagged (stricter when a balance column exists). You decide; nothing is auto-removed.
- Exclude a row: it leaves all totals but stays listed as excluded
- Every transaction lands in exactly one bucket, so totals reconcile to the cent
- Gross, refunds, net, income and transfers in/out, per period
- Percentage change withheld, with the reason, when the baseline is zero or negative
- Empty periods, periods outside the file's dates and unequal period lengths are warned about; per-day figures are given
- Category table (net, gross, refunds, counts, averages) that reconciles exactly with net spending
- Insights: headline change, category increases and decreases, new and stopped categories, each with supporting transactions
- Redesigned interface: Overview, a seven-step Analyse workflow, Transactions, Insights and Settings
- Period presets (split in half, last 30 days, latest month, last 7 days) or custom dates
- Clear session data button

### Partially implemented
- **Responsive layout:** cards and charts reflow on narrow screens. The editable table needs horizontal scrolling on phones.
- **Category rules:** a starter set of Australian merchants. Unknown merchants need manual categories.
- **Duplicate handling:** flags exact matches only. It does not detect the same transaction appearing in two separate files.

### Planned (not in v0.7)
- Frequency vs average value split, recurring payments and subscriptions, unusual transactions (v0.8)
- AI explanation layer over verified facts (v0.9)
- Saved history, user accounts, bank connections, multi-currency (v1.x)

---

## Privacy and limitations
- Uploaded files are held only in this browser session's memory. They are not written to disk, and `st.cache_data` is deliberately not used.
- No fonts, scripts or analytics are loaded from third-party servers. Streamlit usage statistics are turned off in `.streamlit/config.toml`.
- Secure deletion and session isolation have not been independently verified. Avoid uploading highly sensitive data.
- Classification suggestions are rules, not decisions. Review flagged rows before relying on insights.
- Refunds are counted by the date they arrive. They are not matched to the original purchase.
- This is a prototype and not financial advice.

## Changes from v0.6
- Logic moved out of the single script into the `marwick` engine package and the `ui` package
- Fixed: negative "refunds" vanishing from totals; cashback/return wording creating refunds; keywords matching inside words (`NAVIGATOR` → Groceries, `CURRENT` → Housing); review flags not shown; misleading % change on a negative baseline; headline vs category totals not reconciling; corrections reset by settings changes; no duplicate handling; floating-point money
