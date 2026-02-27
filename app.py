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

# Wing Filter
wings = run_query("SELECT DISTINCT wing FROM flats ORDER BY wing;")
wing_list = wings["wing"].tolist()
selected_wing = st.sidebar.selectbox("Select Wing", ["All"] + wing_list)

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
    lambda x: f"{x['wing']} {x['flat_no']} - {x['owner_name']}",
    axis=1
).tolist()

selected_flat_display = st.sidebar.selectbox(
    "Select Flat",
    ["None"] + flat_options
)

# =====================================================
# FLAT-WISE 4 FUND OUTSTANDING TABLE
# =====================================================
st.subheader("📊 Flat-wise Outstanding (Separate Funds)")

flat_balance_df = run_query("""
    SELECT 
        f.owner_name,

        SUM(CASE 
            WHEN ve.ledger_name = f.owner_name 
            THEN ve.amount ELSE 0 END) AS maintenance,

        SUM(CASE 
            WHEN ve.ledger_name LIKE f.owner_name || ' - Interest%%'
            THEN ve.amount ELSE 0 END) AS maintenance_interest,

        SUM(CASE 
            WHEN ve.ledger_name LIKE f.owner_name || ' (Major Repair Fund)%%'
            AND ve.ledger_name NOT LIKE '%%Int.%%'
            THEN ve.amount ELSE 0 END) AS major_repair,

        SUM(CASE 
            WHEN ve.ledger_name LIKE f.owner_name || ' (Major Repair Fund - Int.%%'
            THEN ve.amount ELSE 0 END) AS major_repair_interest

    FROM flats f
    LEFT JOIN vouchers v ON v.flat_id = f.id
    LEFT JOIN voucher_entries ve ON ve.voucher_id = v.id
    WHERE v.voucher_date BETWEEN %s AND %s
    GROUP BY f.owner_name
    ORDER BY f.owner_name
""", (from_date, to_date))

if not flat_balance_df.empty:

    flat_balance_df = flat_balance_df.fillna(0)

    st.dataframe(
        flat_balance_df.rename(columns={
            "owner_name": "Flat Owner",
            "maintenance": "Maintenance",
            "maintenance_interest": "Maint. Interest",
            "major_repair": "Major Repair Fund",
            "major_repair_interest": "MRF Interest"
        })
    )

# =====================================================
# LEDGER STATEMENT (SELECTED FLAT)
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

    flat_id = int(selected_row["id"])
    owner_name = selected_row["owner_name"]

    ledger_type = st.selectbox(
        "Select Ledger Type",
        [
            "Maintenance",
            "Maintenance Interest",
            "Major Repair Fund",
            "Major Repair Fund Interest"
        ]
    )

    # Ledger Pattern Mapping
    if ledger_type == "Maintenance":
        pattern = owner_name

    elif ledger_type == "Maintenance Interest":
        pattern = owner_name + " - Interest%"

    elif ledger_type == "Major Repair Fund":
        pattern = owner_name + " (Major Repair Fund)%"

    elif ledger_type == "Major Repair Fund Interest":
        pattern = owner_name + " (Major Repair Fund - Int.%"

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
        AND ve.ledger_name LIKE %s
        ORDER BY v.voucher_date, v.id
    """, (flat_id, from_date, to_date, pattern))

    if not ledger_df.empty:

        running_balance = 0
        rows = []

        for _, row in ledger_df.iterrows():

            amount = row["amount"]
            running_balance += amount

            rows.append({
                "Date": row["voucher_date"],
                "Voucher Type": row["voucher_type"],
                "Voucher No": row["voucher_no"],
                "Ledger": row["ledger_name"],
                "Debit": abs(amount) if amount < 0 else 0,
                "Credit": amount if amount > 0 else 0,
                "Running Balance": running_balance
            })

        final_df = pd.DataFrame(rows)
        st.dataframe(final_df)

    else:
        st.info("No transactions found for selected period.")