import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- CONFIGURATION & DATABASE INIT ---
st.set_page_config(page_title="SAP HANA-Style Warehouse ERP", layout="wide", page_icon="🏭")

def init_db():
    conn = sqlite3.connect("warehouse_erp.db")
    cursor = conn.cursor()
    # Master Data Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_master (
            material_id TEXT PRIMARY KEY,
            description TEXT,
            uom TEXT,
            safety_stock REAL
        )
    """)
    # Transactional Ledger (SAP Material Ledger style)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_ledger (
            mov_doc TEXT PRIMARY KEY,
            posting_date TEXT,
            material_id TEXT,
            movement_type TEXT, -- 101: Inward, 201: Outward, 561: Init/Reconcile
            qty REAL,
            storage_location TEXT,
            reference TEXT,
            user_id TEXT
        )
    """)
    
    # Insert Dummy Materials if empty
    cursor.execute("SELECT COUNT(*) FROM material_master")
    if cursor.fetchone()[0] == 0:
        materials = [
            ("MAT-001", "Premium Steel Sheet Gr.5", "PCS", 50.0),
            ("MAT-002", "Industrial Copper Wire 10mm", "METERS", 200.0),
            ("MAT-003", "High-Density Polyethylene Resins", "KG", 500.0)
        ]
        cursor.executemany("INSERT INTO material_master VALUES (?, ?, ?, ?)", materials)
        # Initial Stock Upload (SAP Movement Type 561)
        cursor.execute("INSERT INTO stock_ledger VALUES ('DOC-56101', '2026-10-01', 'MAT-001', '561 (Initial Upload)', 150.0, 'SLOC-01', 'System Migration', 'SAP_BATCH')")
        cursor.execute("INSERT INTO stock_ledger VALUES ('DOC-56102', '2026-10-01', 'MAT-002', '561 (Initial Upload)', 1200.0, 'SLOC-01', 'System Migration', 'SAP_BATCH')")
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect("warehouse_erp.db")

# --- CUSTOM SAP HANA CSS STYLE ---
st.markdown("""
    <style>
    .sap-header { background-color: #0a2240; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    .stButton>button { background-color: #0070d2; color: white; border-radius: 4px; }
    </style>
""", unsafe_with_html=True)

st.markdown('<div class="sap-header"><h1>SAP HANA Material Management (MM) Dashboard</h1></div>', unsafe_with_html=True)

# --- SIDEBAR NAVIGATION (SAP T-Codes Style) ---
st.sidebar.image("https://sap.com", width=80)
st.sidebar.title("SAP Easy Access")
menu = st.sidebar.radio(
    "Navigation Menu",
    ["Dashboard & Analytics", "MIGO - Material Inward", "MB1A - Material Outward", "MI07 - Stock Reconciliation", "MB51 - Stock Ledger Document Search"]
)

# --- CONTROLLER LOGIC ---
conn = get_db_connection()
materials_df = pd.read_sql_query("SELECT * FROM material_master", conn)
ledger_all = pd.read_sql_query("SELECT * FROM stock_ledger", conn)

# Calculate real-time stock balances 
# (Movement 101 and 561 add stock; 201 subtracts stock)
def calculate_current_stock(df):
    if df.empty:
        return pd.DataFrame(columns=['material_id', 'Current Stock'])
    df['signed_qty'] = df.apply(lambda row: -row['qty'] if '201' in row['movement_type'] else row['qty'], axis=1)
    balances = df.groupby(['material_id', 'storage_location'])['signed_qty'].sum().reset_index()
    balances.rename(columns={'signed_qty': 'unrestricted_stock'}, inplace=True)
    return balances

stock_balances = calculate_current_stock(ledger_all)

# --- MODULE 1: DASHBOARD & ANALYTICS ---
if menu == "Dashboard & Analytics":
    st.subheader("Global Stock Overview (SAP MM-HANA Live View)")
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Material SKUs Active", len(materials_df))
    col2.metric("Total Warehoused Transactions", len(ledger_all))
    col3.metric("Storage Locations (SLocs) Tracked", stock_balances['storage_location'].nunique() if not stock_balances.empty else 0)
    
    st.write("### Current Unrestricted Stock inventory Balance")
    display_df = pd.merge(stock_balances, materials_df, on="material_id", how="left")
    st.dataframe(display_df, use_container_width=True)

# --- MODULE 2: MATERIAL INWARD (MIGO - 101) ---
elif menu == "MIGO - Material Inward":
    st.subheader("MIGO - Goods Receipt (Movement Type 101)")
    
    with st.form("inward_form", clear_on_submit=True):
        mat_selection = st.selectbox("Select Material Component", materials_df['material_id'] + " - " + materials_df['description'])
        mat_id = mat_selection.split(" - ")[0]
        sloc = st.selectbox("Target Storage Location", ["SLOC-01 (Main Whse)", "SLOC-02 (Cold Storage)", "SLOC-03 (Scrap Yard)"])
        qty = st.number_input("Receipt Quantity", min_value=0.1, step=1.0)
        ref = st.text_input("Purchase Order (PO) / Delivery Note Ref Code")
        submit = st.form_submit_button("Post Goods Receipt (101)")
        
        if submit:
            doc_id = f"DOC-101{int(datetime.now().timestamp())}"
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO stock_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mat_id, "101 (Goods Receipt)", qty, sloc.split(" ")[0], ref, "SAP_USER_MM")
            )
            conn.commit()
            st.success(f"Success: Material Document {doc_id} posted successfully under Movement Type 101.")

# --- MODULE 3: MATERIAL OUTWARD (MB1A - 201) ---
elif menu == "MB1A - Material Outward":
    st.subheader("MB1A - Goods Issue for Consumption (Movement Type 201)")
    
    with st.form("outward_form", clear_on_submit=True):
        mat_selection = st.selectbox("Select Material Component", materials_df['material_id'] + " - " + materials_df['description'])
        mat_id = mat_selection.split(" - ")[0]
        sloc = st.selectbox("Source Storage Location", ["SLOC-01 (Main Whse)", "SLOC-02 (Cold Storage)", "SLOC-03 (Scrap Yard)"])
        qty_to_issue = st.number_input("Issue Quantity", min_value=0.1, step=1.0)
        ref = st.text_input("Cost Center / Production Order Document Target")
        submit = st.form_submit_button("Post Goods Issue (201)")
        
        if submit:
            # Check current inventory balance constraints
            match = stock_balances[(stock_balances['material_id'] == mat_id) & (stock_balances['storage_location'] == sloc.split(" ")[0])]
            available = match['unrestricted_stock'].values[0] if not match.empty else 0.0
            
            if qty_to_issue > available:
                st.error(f"SAP Deficit Error: Goods Issue aborted. Requested quantity exceeds current available stock ({available} remaining).")
            else:
                doc_id = f"DOC-201{int(datetime.now().timestamp())}"
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO stock_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mat_id, "201 (Goods Issue)", qty_to_issue, sloc.split(" ")[0], ref, "SAP_USER_MM")
                )
                conn.commit()
                st.success(f"Success: Material Document {doc_id} generated. Stock updated downstream.")

# --- MODULE 4: STOCK RECONCILIATION (MI07) ---
elif menu == "MI07 - Stock Reconciliation":
    st.subheader("MI07 - Physical Inventory Difference Posting")
    st.info("This interface aligns physical floor count discrepancies by auto-calculating delta movement postings.")
    
    with st.form("recon_form", clear_on_submit=True):
        mat_selection = st.selectbox("Select Target Material", materials_df['material_id'] + " - " + materials_df['description'])
        mat_id = mat_selection.split(" - ")[0]
        sloc = st.selectbox("Target Storage Location Slot", ["SLOC-01", "SLOC-02", "SLOC-03"])
        physical_count = st.number_input("Actual Book-Count Found physically on Floor", min_value=0.0, step=1.0)
        ref = st.text_input("Audit Batch ID / Discrepancy Reason Statement")
        submit = st.form_submit_button("Post Inventory Correction Document")
        
        if submit:
            match = stock_balances[(stock_balances['material_id'] == mat_id) & (stock_balances['storage_location'] == sloc)]
            book_qty = match['unrestricted_stock'].values[0] if not match.empty else 0.0
            variance = physical_count - book_qty
            
            if variance == 0:
                st.info("Zero delta variance identified. Database alignment unnecessary.")
            else:
                mov_type = "701 (Physical Gain)" if variance > 0 else "702 (Physical Loss)"
                doc_id = f"DOC-MI07{int(datetime.now().timestamp())}"
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO stock_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mat_id, mov_type, abs(variance), sloc, f"Variance Balance Fix: {ref}", "SAP_AUDITOR")
                )
                conn.commit()
                st.success(f"Inventory Adjusted! Material Document {doc_id} created with movement adjustment flag {mov_type} for absolute variance of {abs(variance)} units.")

# --- MODULE 5: STOCK LEDGER SEARCH (MB51) ---
elif menu == "MB51 - Stock Ledger Document Search":
    st.subheader("MB51 - Material Document Audit Trail Ledger")
    
    search_query = st.text_input("Filter Ledger Logs by Material Code / Document ID / Mov Type Key").strip()
    
    if search_query:
        filtered_df = ledger_all[
            ledger_all['material_id'].str.contains(search_query, case=False) |
            ledger_all['mov_doc'].str.contains(search_query, case=False) |
            ledger_all['movement_type'].str.contains(search_query, case=False)
        ]
    else:
        filtered_df = ledger_all
        
