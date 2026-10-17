"""Personal Finance Tracker - a local Streamlit + SQLite app.

All data is stored in finance.db next to this file. No login, no cloud, no external APIs.
Run with:  streamlit run app.py
"""

import io
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).with_name("finance.db")
CATEGORIES = ["Salary", "Food", "Rent", "Transport", "Bills", "Shopping",
              "Health", "Education", "Entertainment", "Other"]
TYPES = ["Income", "Expense"]
CSV_COLUMNS = ["date", "amount", "type", "category", "note"]
MAX_AMOUNT = 1_000_000_000  # sanity cap: ₹100 crore


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def format_inr(value: float, decimals: int = 2) -> str:
    """Format a number in Indian style, e.g. 1234567.5 -> ₹12,34,567.50."""
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if decimals else "")


def month_label(ym: str) -> str:
    """'2026-10' -> 'Oct 2026'."""
    return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")


def shift_month(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    total = y * 12 + (m - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT NOT NULL,
                amount   REAL NOT NULL CHECK (amount > 0),
                type     TEXT NOT NULL CHECK (type IN ('Income', 'Expense')),
                category TEXT NOT NULL CHECK (category <> ''),
                note     TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                amount   REAL NOT NULL CHECK (amount >= 0)
            );
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        seeded = conn.execute("SELECT value FROM meta WHERE key = 'seeded'").fetchone()
        if not seeded:
            seed_sample_data(conn)
            conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', '1')")


def seed_sample_data(conn: sqlite3.Connection) -> None:
    """Insert 20 sample transactions spread over the last 6 months, plus sample budgets."""
    this_month = date.today().strftime("%Y-%m")
    # (months ago, day, amount, type, category, note)
    samples = [
        (5, 1, 65000, "Income", "Salary", "Monthly salary"),
        (5, 5, 18000, "Expense", "Rent", "House rent"),
        (5, 12, 4200, "Expense", "Food", "Groceries"),
        (4, 1, 65000, "Income", "Salary", "Monthly salary"),
        (4, 5, 18000, "Expense", "Rent", "House rent"),
        (4, 18, 7499, "Expense", "Shopping", "Festival shopping"),
        (3, 1, 65000, "Income", "Salary", "Monthly salary"),
        (3, 5, 18000, "Expense", "Rent", "House rent"),
        (3, 21, 2350, "Expense", "Health", "Pharmacy"),
        (2, 1, 68000, "Income", "Salary", "Salary after increment"),
        (2, 5, 18000, "Expense", "Rent", "House rent"),
        (2, 15, 12500, "Expense", "Education", "Online course fee"),
        (1, 1, 68000, "Income", "Salary", "Monthly salary"),
        (1, 5, 18000, "Expense", "Rent", "House rent"),
        (1, 20, 3100, "Expense", "Bills", "Electricity and internet"),
        (0, 1, 68000, "Income", "Salary", "Monthly salary"),
        (0, 3, 18000, "Expense", "Rent", "House rent"),
        (0, 4, 5200, "Expense", "Food", "Groceries and dining out"),
        (0, 6, 1850, "Expense", "Transport", "Metro card and cabs"),
        (0, 8, 1499, "Expense", "Entertainment", "Movie and OTT subscription"),
    ]
    rows = []
    for months_ago, day, amount, ttype, cat, note in samples:
        ym = shift_month(this_month, -months_ago)
        d = f"{ym}-{day:02d}"
        if d > date.today().isoformat():  # never seed a future date
            d = date.today().isoformat()
        rows.append((d, amount, ttype, cat, note))
    conn.executemany(
        "INSERT INTO transactions (date, amount, type, category, note) VALUES (?, ?, ?, ?, ?)", rows
    )
    budgets = {"Food": 6000, "Rent": 18000, "Transport": 2000, "Bills": 3500, "Shopping": 5000,
               "Health": 3000, "Education": 10000, "Entertainment": 1500, "Other": 2000}
    conn.executemany("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)",
                     budgets.items())


def validate(d, amount, ttype, category) -> list[str]:
    """Return a list of validation errors (empty list means valid)."""
    errors = []
    try:
        datetime.strptime(str(d), "%Y-%m-%d")
    except ValueError:
        errors.append("Date must be in YYYY-MM-DD format.")
    try:
        amt = float(amount)
        if pd.isna(amt) or amt <= 0:
            errors.append("Amount must be greater than zero (no negative or zero amounts).")
        elif amt > MAX_AMOUNT:
            errors.append(f"Amount cannot exceed {format_inr(MAX_AMOUNT, 0)}.")
    except (TypeError, ValueError):
        errors.append("Amount must be a number.")
    if ttype not in TYPES:
        errors.append("Type must be Income or Expense.")
    if not category or not str(category).strip():
        errors.append("Category cannot be empty.")
    elif category not in CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(CATEGORIES)}.")
    return errors


def add_transaction(d, amount, ttype, category, note) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO transactions (date, amount, type, category, note) VALUES (?, ?, ?, ?, ?)",
            (str(d), round(float(amount), 2), ttype, category, (note or "").strip()),
        )


def update_transaction(tid, d, amount, ttype, category, note) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE transactions SET date=?, amount=?, type=?, category=?, note=? WHERE id=?",
            (str(d), round(float(amount), 2), ttype, category, (note or "").strip(), tid),
        )


def delete_transaction(tid) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id=?", (tid,))


def load_transactions() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, date, amount, type, category, note FROM transactions "
            "ORDER BY date DESC, id DESC", conn)
    df["note"] = df["note"].fillna("")
    df["month"] = df["date"].str[:7]
    return df


def load_budgets() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT category, amount FROM budgets").fetchall()
    return {r["category"]: r["amount"] for r in rows}


def save_budgets(budgets: dict) -> None:
    with get_conn() as conn:
        conn.executemany("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)",
                         budgets.items())


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------
def available_months(df: pd.DataFrame) -> list[str]:
    months = set(df["month"].tolist()) | {date.today().strftime("%Y-%m")}
    return sorted(months, reverse=True)


def budget_status(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    """Spending vs budget per category for one month."""
    budgets = load_budgets()
    spent = (df[(df["month"] == ym) & (df["type"] == "Expense")]
             .groupby("category")["amount"].sum())
    rows = []
    for cat in CATEGORIES:
        b = budgets.get(cat, 0) or 0
        s = float(spent.get(cat, 0))
        if b <= 0 and s == 0:
            continue
        pct = (s / b * 100) if b > 0 else None
        rows.append({"category": cat, "budget": b, "spent": s, "pct": pct})
    return pd.DataFrame(rows, columns=["category", "budget", "spent", "pct"])


def show_budget_alerts(df: pd.DataFrame, ym: str) -> None:
    status = budget_status(df, ym)
    any_alert = False
    for _, r in status.iterrows():
        if r["pct"] is None or pd.isna(r["pct"]):
            continue
        msg = (f"**{r['category']}**: spent {format_inr(r['spent'])} of "
               f"{format_inr(r['budget'])} budget ({r['pct']:.0f}%)")
        if r["pct"] >= 100:
            st.error(f"🚨 Budget reached or exceeded — {msg}")
            any_alert = True
        elif r["pct"] >= 80:
            st.warning(f"⚠️ Nearing budget — {msg}")
            any_alert = True
    if not any_alert and not status.empty:
        st.success(f"All categories are within 80% of budget for {month_label(ym)}.")


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["id", "date", "type", "category", "amount", "note"]].copy()
    out["amount"] = out["amount"].map(format_inr)
    return out.rename(columns={"id": "ID", "date": "Date", "type": "Type",
                               "category": "Category", "amount": "Amount (₹)", "note": "Note"})


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_dashboard(df: pd.DataFrame) -> None:
    st.header("📊 Dashboard")
    months = available_months(df)
    ym = st.selectbox("Month", months, format_func=month_label, key="dash_month")
    mdf = df[df["month"] == ym]

    income = mdf.loc[mdf["type"] == "Income", "amount"].sum()
    expense = mdf.loc[mdf["type"] == "Expense", "amount"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Income", format_inr(income))
    c2.metric("Total Expense", format_inr(expense))
    c3.metric("Balance", format_inr(income - expense))

    st.subheader("Budget alerts")
    show_budget_alerts(df, ym)

    left, right = st.columns(2)
    with left:
        st.subheader(f"Expenses by category — {month_label(ym)}")
        exp = (mdf[mdf["type"] == "Expense"].groupby("category", as_index=False)["amount"].sum()
               .sort_values("amount", ascending=False))
        if exp.empty:
            st.info("No expenses recorded for this month.")
        else:
            exp["label"] = exp["amount"].map(format_inr)
            fig = px.pie(exp, names="category", values="amount", hole=0.4,
                         custom_data=["label"])
            fig.update_traces(hovertemplate="%{label}: %{customdata[0]} (%{percent})<extra></extra>",
                              textinfo="percent+label")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("Last 6 months — Income vs Expense")
        last6 = [shift_month(ym, -i) for i in range(5, -1, -1)]
        sub = df[df["month"].isin(last6)]
        pivot = (sub.pivot_table(index="month", columns="type", values="amount",
                                 aggfunc="sum", fill_value=0)
                 .reindex(index=last6, columns=TYPES, fill_value=0))
        x = [month_label(m) for m in last6]
        fig = go.Figure()
        for ttype, color in (("Income", "#2e9e5b"), ("Expense", "#d9534f")):
            vals = pivot[ttype].tolist()
            fig.add_bar(name=ttype, x=x, y=vals, marker_color=color,
                        customdata=[format_inr(v) for v in vals],
                        hovertemplate="%{x}<br>" + ttype + ": %{customdata}<extra></extra>")
        fig.update_layout(barmode="group", margin=dict(t=10, b=10, l=10, r=10),
                          yaxis_title="Amount (₹)", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")


def page_add(df: pd.DataFrame) -> None:
    st.header("➕ Add Transaction")
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Date", value=date.today(), format="DD/MM/YYYY")
        amount = c2.number_input("Amount (₹)", min_value=0.0, step=100.0, format="%.2f")
        ttype = c1.radio("Type", TYPES, index=1, horizontal=True)
        category = c2.selectbox("Category", CATEGORIES, index=None,
                                placeholder="Choose a category")
        note = st.text_input("Note (optional)", max_chars=200)
        submitted = st.form_submit_button("Add transaction", type="primary")

    if submitted:
        errors = validate(d, amount, ttype, category)
        if errors:
            for e in errors:
                st.error(e)
            return
        add_transaction(d, amount, ttype, category, note)
        st.success(f"Added {ttype.lower()} of {format_inr(amount)} under {category}.")
        if ttype == "Expense":
            ym = d.strftime("%Y-%m")
            status = budget_status(load_transactions(), ym)
            row = status[status["category"] == category]
            if not row.empty and row.iloc[0]["pct"] is not None and not pd.isna(row.iloc[0]["pct"]):
                pct = row.iloc[0]["pct"]
                msg = (f"{category} spending for {month_label(ym)} is now "
                       f"{format_inr(row.iloc[0]['spent'])} of {format_inr(row.iloc[0]['budget'])} "
                       f"({pct:.0f}%).")
                if pct >= 100:
                    st.error(f"🚨 Budget reached or exceeded! {msg}")
                elif pct >= 80:
                    st.warning(f"⚠️ Nearing budget. {msg}")


def page_transactions(df: pd.DataFrame) -> None:
    st.header("📋 Transactions")
    c1, c2 = st.columns(2)
    months = ["All"] + available_months(df)
    ym = c1.selectbox("Month", months,
                      format_func=lambda m: "All months" if m == "All" else month_label(m))
    cats = c2.multiselect("Category", CATEGORIES, placeholder="All categories")

    view = df
    if ym != "All":
        view = view[view["month"] == ym]
    if cats:
        view = view[view["category"].isin(cats)]

    inc = view.loc[view["type"] == "Income", "amount"].sum()
    exp = view.loc[view["type"] == "Expense", "amount"].sum()
    st.caption(f"{len(view)} transactions · Income {format_inr(inc)} · "
               f"Expense {format_inr(exp)} · Net {format_inr(inc - exp)}")

    if view.empty:
        st.info("No transactions match these filters.")
        return
    st.dataframe(display_table(view), hide_index=True, width="stretch")

    st.subheader("Edit or delete a transaction")
    options = view["id"].tolist()
    lookup = view.set_index("id")
    tid = st.selectbox(
        "Select transaction", options,
        format_func=lambda i: (f"#{i} · {lookup.at[i, 'date']} · {lookup.at[i, 'type']} · "
                               f"{lookup.at[i, 'category']} · {format_inr(lookup.at[i, 'amount'])}"),
    )
    row = lookup.loc[tid]

    with st.form(f"edit_form_{tid}"):
        c1, c2 = st.columns(2)
        d = c1.date_input("Date", value=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                          format="DD/MM/YYYY")
        amount = c2.number_input("Amount (₹)", min_value=0.0, step=100.0, format="%.2f",
                                 value=float(row["amount"]))
        ttype = c1.radio("Type", TYPES, index=TYPES.index(row["type"]), horizontal=True)
        category = c2.selectbox(
            "Category", CATEGORIES,
            index=CATEGORIES.index(row["category"]) if row["category"] in CATEGORIES else None)
        note = st.text_input("Note", value=row["note"], max_chars=200)
        b1, b2 = st.columns(2)
        save = b1.form_submit_button("💾 Save changes", type="primary")
        confirm = b2.checkbox("Yes, I want to delete this")
        delete = b2.form_submit_button("🗑️ Delete")

    if save:
        errors = validate(d, amount, ttype, category)
        if errors:
            for e in errors:
                st.error(e)
        else:
            update_transaction(tid, d, amount, ttype, category, note)
            st.session_state["flash"] = f"Transaction #{tid} updated."
            st.rerun()
    if delete:
        if not confirm:
            st.warning("Tick the confirmation box to delete.")
        else:
            delete_transaction(tid)
            st.session_state["flash"] = f"Transaction #{tid} deleted."
            st.rerun()


def page_budgets(df: pd.DataFrame) -> None:
    st.header("🎯 Monthly Budgets")
    st.write("Set a monthly spending limit for each category (₹0 means no budget). "
             "You get a warning at 80% and an alert at 100%.")
    budgets = load_budgets()
    with st.form("budget_form"):
        cols = st.columns(3)
        new = {}
        for i, cat in enumerate(c for c in CATEGORIES if c != "Salary"):
            new[cat] = cols[i % 3].number_input(
                cat, min_value=0.0, step=500.0, format="%.0f",
                value=float(budgets.get(cat, 0) or 0), key=f"budget_{cat}")
        if st.form_submit_button("Save budgets", type="primary"):
            if any(v < 0 for v in new.values()):
                st.error("Budgets cannot be negative.")
            else:
                save_budgets(new)
                st.success("Budgets saved.")

    st.subheader("Budget usage")
    ym = st.selectbox("Month", available_months(df), format_func=month_label, key="budget_month")
    status = budget_status(df, ym)
    status = status[status["budget"] > 0]
    if status.empty:
        st.info("No budgets set yet.")
        return
    for _, r in status.iterrows():
        pct = r["pct"]
        icon = "🚨" if pct >= 100 else "⚠️" if pct >= 80 else "✅"
        st.write(f"{icon} **{r['category']}** — {format_inr(r['spent'])} of "
                 f"{format_inr(r['budget'])} ({pct:.0f}%)")
        st.progress(min(pct / 100, 1.0))
    show_budget_alerts(df, ym)


def page_import_export(df: pd.DataFrame) -> None:
    st.header("📁 Import / Export")

    st.subheader("Export")
    export = df[CSV_COLUMNS].sort_values("date")
    st.download_button(
        "⬇️ Download all transactions (CSV)",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"transactions_{date.today().isoformat()}.csv",
        mime="text/csv", disabled=export.empty)
    st.caption(f"{len(export)} transactions. Columns: {', '.join(CSV_COLUMNS)}")

    st.subheader("Import")
    st.write("Upload a CSV with columns **date, amount, type, category, note**. "
             "Date must be YYYY-MM-DD, amount positive, type Income/Expense, and category one of: "
             + ", ".join(CATEGORIES) + ".")
    sample = pd.DataFrame([["2026-10-01", 50000, "Income", "Salary", "October salary"],
                           ["2026-10-02", 450.5, "Expense", "Food", "Lunch"]],
                          columns=CSV_COLUMNS)
    st.download_button("Download a sample template", sample.to_csv(index=False).encode("utf-8"),
                       file_name="sample_template.csv", mime="text/csv")

    uploaded = st.file_uploader("Choose CSV file", type=["csv"])
    skip_dupes = st.checkbox("Skip rows that already exist (same date, amount, type, category, note)",
                             value=True)
    if uploaded is None:
        return
    try:
        raw = pd.read_csv(io.BytesIO(uploaded.getvalue()), dtype=str, keep_default_na=False,
                          encoding="utf-8-sig")
    except Exception as e:  # malformed file
        st.error(f"Could not read the CSV file: {e}")
        return
    raw.columns = [c.strip().lower() for c in raw.columns]
    missing = [c for c in CSV_COLUMNS if c != "note" and c not in raw.columns]
    if missing:
        st.error(f"Missing required column(s): {', '.join(missing)}")
        return
    if "note" not in raw.columns:
        raw["note"] = ""

    existing = {(r.date, round(r.amount, 2), r.type, r.category, r.note)
                for r in df.itertuples()}
    good, bad, dupes = [], [], 0
    for i, r in raw.iterrows():
        d = r["date"].strip()
        try:  # accept DD/MM/YYYY and DD-MM-YYYY too, store as ISO
            d = pd.to_datetime(d, format="mixed", dayfirst="/" in d or d[2:3] == "-").strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
        amt = r["amount"].replace(",", "").replace("₹", "").strip()
        ttype = r["type"].strip().title()
        cat = r["category"].strip().title()
        note = r["note"].strip()
        errors = validate(d, amt, ttype, cat)
        if errors:
            bad.append({"row": i + 2, "errors": " ".join(errors)})
            continue
        key = (d, round(float(amt), 2), ttype, cat, note)
        if skip_dupes and key in existing:
            dupes += 1
            continue
        existing.add(key)
        good.append(key)

    st.write(f"**Preview:** {len(good)} valid rows, {len(bad)} invalid rows, "
             f"{dupes} duplicates skipped.")
    if bad:
        st.warning("These rows will be skipped:")
        st.dataframe(pd.DataFrame(bad), hide_index=True, width="stretch")
    if good and st.button(f"Import {len(good)} transactions", type="primary"):
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO transactions (date, amount, type, category, note) "
                "VALUES (?, ?, ?, ?, ?)", good)
        st.session_state["flash"] = f"Imported {len(good)} transactions."
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Finance Tracker", page_icon="💰", layout="wide")
    init_db()
    df = load_transactions()

    st.sidebar.title("💰 Finance Tracker")
    pages = {"Dashboard": page_dashboard, "Add Transaction": page_add,
             "Transactions": page_transactions, "Budgets": page_budgets,
             "Import / Export": page_import_export}
    choice = st.sidebar.radio("Go to", list(pages))
    st.sidebar.caption(f"Data stored locally in `{DB_PATH.name}`")

    if msg := st.session_state.pop("flash", None):
        st.success(msg)
    pages[choice](df)


if __name__ == "__main__":
    main()
