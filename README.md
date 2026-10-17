# Personal Finance Tracker

A simple, private finance tracker that runs entirely on your computer.
Built with Python, Streamlit and SQLite. No login, no cloud, no external APIs —
all data is saved in a local file called `finance.db` next to `app.py`.

## Features

- Add transactions (date, amount, Income/Expense, category, note)
- Transactions table with month and category filters, plus edit and delete
- Dashboard: monthly income, expense and balance; expense pie chart; 6-month income vs expense bar chart
- Monthly budget per category with warnings at 80% and alerts at 100%
- Export all transactions to CSV and import from CSV
- Indian Rupee (₹) with Indian number formatting (e.g. ₹1,23,456.00)
- 20 sample transactions loaded on first run so the charts are filled

## Requirements

- Python 3.10 or newer ([python.org/downloads](https://www.python.org/downloads/))

## Install and run

### Windows (Command Prompt or PowerShell)

```
cd path\to\Finance-tracker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### macOS / Linux

```
cd path/to/Finance-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens in your browser at http://localhost:8501.
`.streamlit/config.toml` keeps it local-only (bound to localhost, Streamlit usage statistics off).
Stop it with `Ctrl + C` in the terminal.

### Running it again later

Only the activate and run steps are needed:

```
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
streamlit run app.py
```

## CSV format (import/export)

```
date,amount,type,category,note
2026-10-01,50000,Income,Salary,October salary
2026-10-02,450.50,Expense,Food,Lunch
```

- `date`: YYYY-MM-DD (DD/MM/YYYY is also accepted on import)
- `amount`: positive number
- `type`: Income or Expense
- `category`: Salary, Food, Rent, Transport, Bills, Shopping, Health, Education, Entertainment, Other
- `note`: optional

Invalid rows are listed and skipped; duplicates can be skipped automatically.

## Backup and reset

- **Backup:** copy `finance.db` somewhere safe, or use Export to CSV.
- **Start fresh:** stop the app and delete `finance.db`. Sample data is added again on the next start.
