import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

# =====================================================
# LOGIN
# =====================================================
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    password = st.text_input("Enter Password", type="password")
    if password == st.secrets["APP_PASSWORD"]:
        st.session_state.auth = True
        st.rerun()
    else:
        st.stop()

# =====================================================
# DATABASE CONNECTION
# =====================================================
@st.cache_resource
def get_connection():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"],
        database=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"]
    )

conn = get_connection()

def run_query(query, params=None):
    return pd.read_sql(query, conn, params=params)

def format_balance(x):
    if x < 0:
        return f"{abs(x):,.2f} Dr"
    elif x > 0:
        return f"{abs(x):,.2f} Cr"
    else:
        return "0.00"

st.title("🏢 Society ERP Dashboard")

# =====================================================
# SIDEBAR FILTERS
# =====================================================
st.sidebar.header("Filters")

from_date = st.sidebar.date_input("From Date", date(2025, 4, 1))
to_date = st.sidebar.date_input("To Date", date.today())

# =====================================================
# FETCH DISTINCT FLATS (SAFE)
# =====================================================
flats_query = """
    SELECT DISTINCT 
        flat_code,
        SPLIT_PART(flat_code, ' ', 1) AS wing
    FROM ledger_transactions
    WHERE flat_code IS NOT NULL
    ORDER BY flat_code
"""

flats_df = run_query(flats_query)

if flats_df.empty:
    st.error("No flat data found in ledger_transactions table.")
    st.stop()

wing_list = sorted(flats_df["wing"].dropna().unique().tolist())

selected_wing = st.sidebar.selectbox(
    "Select Wing",
    ["All"] + wing_list
)

if selected_wing != "All":
    flats_df = flats_df[flats_df["wing"] == selected_wing]

flat_list = flats_df["flat_code"].dropna().tolist()

selected_flat = st.sidebar.selectbox(
    "Select Flat",
    ["None"] + flat_list
)

# =====================================================
# SUMMARY TABLE
# =====================================================
st.subheader("📊 Flat-wise Outstanding (Separate Funds)")

summary_query = """
    SELECT 
        flat_code,

        SUM(CASE WHEN fund_type='maintenance' THEN amount ELSE 0 END) AS maintenance,
        SUM(CASE WHEN fund_type='maintenance_interest' THEN amount ELSE 0 END) AS maintenance_interest,
        SUM(CASE WHEN fund_type='mrf' THEN amount ELSE 0 END) AS mrf,
        SUM(CASE WHEN fund_type='mrf_interest' THEN amount ELSE 0 END) AS mrf_interest

    FROM ledger_transactions
    WHERE flat_code IS NOT NULL
    AND transaction_date BETWEEN %s AND %s
    GROUP BY flat_code
    ORDER BY flat_code
"""

flat_balance_df = run_query(summary_query, (from_date, to_date))

if not flat_balance_df.empty:

    flat_balance_df = flat_balance_df.fillna(0)

    for col in ["maintenance", "maintenance_interest", "mrf", "mrf_interest"]:
        flat_balance_df[col] = flat_balance_df[col].apply(format_balance)

    st.dataframe(flat_balance_df, use_container_width=True)
else:
    st.info("No data for selected date range.")

# =====================================================
# LEDGER STATEMENT
# =====================================================
if selected_flat != "None":

    st.subheader("📖 Ledger Statement")

    ledger_type = st.selectbox(
        "Select Ledger Type",
        [
            "Maintenance",
            "Maintenance Interest",
            "Major Repair Fund",
            "Major Repair Fund Interest"
        ]
    )

    fund_map = {
        "Maintenance": "maintenance",
        "Maintenance Interest": "maintenance_interest",
        "Major Repair Fund": "mrf",
        "Major Repair Fund Interest": "mrf_interest"
    }

    fund_key = fund_map[ledger_type]

    ledger_query = """
        SELECT
            transaction_date,
            voucher_type,
            voucher_no,
            amount
        FROM ledger_transactions
        WHERE flat_code = %s
        AND fund_type = %s
        AND transaction_date BETWEEN %s AND %s
        ORDER BY transaction_date, id
    """

    ledger_df = run_query(
        ledger_query,
        (selected_flat, fund_key, from_date, to_date)
    )

    if ledger_df.empty:
        st.info("No transactions found for selected period.")
    else:
        running_balance = 0
        rows = []

        for _, row in ledger_df.iterrows():

            amount = row["amount"]
            running_balance += amount

            rows.append({
                "Date": row["transaction_date"],
                "Voucher Type": row["voucher_type"],
                "Voucher No": row["voucher_no"],
                "Debit": abs(amount) if amount < 0 else 0,
                "Credit": amount if amount > 0 else 0,
                "Balance": f"{abs(running_balance):,.2f} "
                           f"{'Dr' if running_balance < 0 else 'Cr' if running_balance > 0 else ''}"
            })

        final_df = pd.DataFrame(rows)
        st.dataframe(final_df, use_container_width=True)