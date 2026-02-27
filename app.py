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
conn = psycopg2.connect(
    host=st.secrets["DB_HOST"],
    port=st.secrets["DB_PORT"],
    database=st.secrets["DB_NAME"],
    user=st.secrets["DB_USER"],
    password=st.secrets["DB_PASSWORD"]
)

def run_query(query, params=None):
    return pd.read_sql(query, conn, params=params)

st.title("🏢 Society ERP Dashboard")

# =====================================================
# SIDEBAR FILTERS
# =====================================================
st.sidebar.header("Filters")

from_date = st.sidebar.date_input("From Date", date(2025, 4, 1))
to_date = st.sidebar.date_input("To Date", date.today())

# Wing list
wings = run_query("SELECT DISTINCT wing FROM flats ORDER BY wing;")
wing_list = wings["wing"].tolist()
selected_wing = st.sidebar.selectbox("Select Wing", ["All"] + wing_list)

# Flat list (filtered by wing)
if selected_wing == "All":
    flats_df = run_query("""
        SELECT id, wing, flat_no, owner_name 
        FROM flats
        ORDER BY wing, flat_no
    """)
else:
    flats_df = run_query("""
        SELECT id, wing, flat_no, owner_name 
        FROM flats
        WHERE wing = %s
        ORDER BY flat_no
    """, (selected_wing,))

flat_options = flats_df.apply(
    lambda x: f"{x['wing']} {x['flat_no']} - {x['owner_name']}", axis=1
).tolist()

selected_flat_display = st.sidebar.selectbox("Select Flat", ["None"] + flat_options)

# =====================================================
# KPIs
# =====================================================
st.subheader("📊 Society Summary")

total_raw = run_query("""
    SELECT SUM(ve.amount)
    FROM voucher_entries ve
    JOIN vouchers v ON v.id = ve.voucher_id
    WHERE v.voucher_date BETWEEN %s AND %s
""", (from_date, to_date)).iloc[0, 0]

col1, col2 = st.columns(2)

if total_raw is not None:
    if total_raw < 0:
        col1.metric("Total Receivable", f"{abs(total_raw):,.2f} Dr")
    else:
        col1.metric("Total Advance Credit", f"{abs(total_raw):,.2f} Cr")

# =====================================================
# FLAT SUMMARY TABLE
# =====================================================
st.subheader("📋 Flat-wise Balance")

flat_balance_df = run_query("""
    SELECT 
        f.wing,
        f.flat_no,
        f.owner_name,
        SUM(ve.amount) as raw_balance
    FROM flats f
    JOIN vouchers v ON v.flat_id = f.id
    JOIN voucher_entries ve ON ve.voucher_id = v.id
    WHERE v.voucher_date BETWEEN %s AND %s
    GROUP BY f.wing, f.flat_no, f.owner_name
    ORDER BY f.wing, f.flat_no
""", (from_date, to_date))

if not flat_balance_df.empty:
    flat_balance_df["Amount"] = flat_balance_df["raw_balance"].abs().map("{:,.2f}".format)
    flat_balance_df["Type"] = flat_balance_df["raw_balance"].apply(
        lambda x: "Dr" if x < 0 else "Cr" if x > 0 else "Zero"
    )
    st.dataframe(flat_balance_df[["wing", "flat_no", "owner_name", "Amount", "Type"]])

# =====================================================
# LEDGER STATEMENT
# =====================================================
if selected_flat_display != "None":

    st.subheader("📖 Ledger Statement")

    selected_row = flats_df[
        flats_df.apply(
            lambda x: f"{x['wing']} {x['flat_no']} - {x['owner_name']}" 
            == selected_flat_display,
            axis=1
        )
    ].iloc[0]

    flat_id = selected_row["id"]
    flat_name = selected_row["owner_name"]

    ledger_df = run_query("""
        SELECT
            v.voucher_date,
            v.voucher_type,
            v.voucher_no,
            ve.ledger_name,
            ve.amount
        FROM vouchers v
        JOIN voucher_entries ve ON ve.voucher_id = v.id
        WHERE v.flat_id = %s
        AND v.voucher_date BETWEEN %s AND %s
        ORDER BY v.voucher_date, v.id, ve.id
    """, (flat_id, from_date, to_date))

    if not ledger_df.empty:

        running_flat = 0
        running_full = 0
        rows = []

        for _, row in ledger_df.iterrows():
            amount = row["amount"]

            if amount < 0:
                debit = abs(amount)
                credit = 0
            else:
                debit = 0
                credit = amount

            running_full += amount

            if row["ledger_name"] == flat_name:
                running_flat += amount

            rows.append({
                "Date": row["voucher_date"],
                "Type": row["voucher_type"],
                "Voucher No": row["voucher_no"],
                "Ledger": row["ledger_name"],
                "Debit": debit,
                "Credit": credit,
                "Flat Balance": f"{abs(running_flat):,.2f} {'Dr' if running_flat < 0 else 'Cr' if running_flat > 0 else ''}",
                "Full Voucher Balance": f"{abs(running_full):,.2f} {'Dr' if running_full < 0 else 'Cr' if running_full > 0 else ''}"
            })

        final_df = pd.DataFrame(rows)

        st.dataframe(final_df)

    else:
        st.info("No transactions found for selected period.")