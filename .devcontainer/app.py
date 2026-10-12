import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- CODE CONFIGURATION & SAP DESIGN INTERFACE ---
st.set_page_config(
    page_title="SAP S/4HANA - Extended Warehouse Management (EWM)", 
    layout="wide", 
    page_icon="📦"
)

# Custom SAP Fiori-inspired CSS Styling
st.markdown("""
    <style>
    .sap-fiori-header {
        background: linear-gradient(90deg, #1d2d44 0%, #0a1128 100%);
        color: white;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .sap-badge {
        background-color: #0070d2;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-family: monospace;
        font-weight: bold;
    }
    div.stButton > button:first-child {
        background-color: #0070d2;
        color: white;
        font-weight: 500;
        border-radius: 4px;
        border: none;
        padding: 10px 24px;
    }
    div.stButton > button:first-child:hover {
        background-color: #005fb8;
        border: none;
    }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE ORCHESTRATION & SCHEMA ---
def get_db_connection():
    return sqlite3.connect("sap_ewm_warehouse.db")

def initialize_sap_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Material Master Data (SAP MM)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_master (
            material_id TEXT PRIMARY KEY,
            description TEXT,
            uom TEXT,
            safety_stock REAL,
            valuation_price REAL
        )
    """)
    
    # 2. Unified Material Document Ledger (Audit Trail Ledger)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_ledger (
            mat_doc_id TEXT PRIMARY KEY,
            posting_date TEXT,
            material_id TEXT,
            movement_type TEXT,  -- 101: Inward, 201: Outward, 701/702: Physical Adj
            qty REAL,
            storage_location TEXT,
            cost_center TEXT,
            reference_doc TEXT,
            user_id TEXT
        )
    """)
    
    # Seed Initial Master Data if database is completely empty
    cursor.execute("SELECT COUNT(*) FROM material_master")
    if cursor.fetchone()[0] == 0:
        materials = [
            ("MAT-1001", "Heavy Gauge Carbon Steel Coils", "TONS", 10.0, 1250.00),
            ("MAT-2004", "Industrial Copper Wire Spools (50m)", "EA", 100.0, 45.50),
            ("MAT-3090", "High-Density Polyethylene Granules", "KG", 500.0, 3.25),
            ("MAT-4412", "Lithium-Ion Battery Pack Core 48V", "PCS", 25.0, 420.00)
        ]
        cursor.executemany("INSERT INTO material_master VALUES (?, ?, ?, ?, ?)", materials)
        
        # Seed Initial Stock Open Balance (SAP Movement Type 561)
        initial_balances = [
            ("DOC-561-01", datetime.now().strftime("%Y-%m-%d %H:%M"), "MAT-1001", "561 (Initial Stock Upload)", 45.0, "SLOC-A1", "SYSTEM_INIT", "MIG-2026", "SAP_SYSTEM"),
            ("DOC-561-02", datetime.now().strftime("%Y-%m-%d %H:%M"), "MAT-2004", "561 (Initial Stock Upload)", 350.0, "SLOC-A1", "SYSTEM_INIT", "MIG-2026", "SAP_SYSTEM"),
            ("DOC-561-03", datetime.now().strftime("%Y-%m-%d %H:%M"), "MAT-3090", "561 (Initial Stock Upload)", 2500.0, "SLOC-B2", "SYSTEM_INIT", "MIG-2026", "SAP_SYSTEM")
        ]
        cursor.executemany("INSERT INTO material_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", initial_balances)
        
    conn.commit()
    conn.close()

# Execute Database Configuration Init Routine
initialize_sap_database()

# --- REAL-TIME INVENTORY AGGREGATOR ---
def fetch_unrestricted_stock_balances():
    conn = get_db_connection()
    ledger_df = pd.read_sql_query("SELECT * FROM material_ledger", conn)
    master_df = pd.read_sql_query("SELECT * FROM material_master", conn)
    conn.close()
    
    if ledger_df.empty:
        return pd.DataFrame(columns=['material_id', 'description', 'storage_location', 'stock_qty', 'uom', 'total_value'])
    
    # Map directional weights based on SAP movement criteria
    # Positive directional inflows (101, 561, 701) vs Negative directional consumption outflows (201, 702)
    def calculate_signed_quantity(row):
        mv = row['movement_type']
        if "201" in mv or "702" in mv:
            return -row['qty']
        return row['qty']
        
    ledger_df['signed_qty'] = ledger_df.apply(calculate_signed_quantity, axis=1)
    
    # Pivot matrix down into distinct Material ID + Storage Location groupings
    stock_group = ledger_df.groupby(['material_id', 'storage_location'])['signed_qty'].sum().reset_index()
    stock_group.rename(columns={'signed_qty': 'stock_qty'}, inplace=True)
    
    # Merge Master description parameters & calculations
    final_stock_matrix = pd.merge(stock_group, master_df, on="material_id", how="left")
    final_stock_matrix['total_value'] = final_stock_matrix['stock_qty'] * final_stock_matrix['valuation_price']
    
    return final_stock_matrix[['material_id', 'description', 'storage_location', 'stock_qty', 'uom', 'total_value']]

# --- SAP EASY ACCESS PANEL ---
st.markdown("""
    <div class="sap-fiori-header">
        <h2 style='margin:0;'>SAP S/4HANA EWM — Enterprise Resource Planner</h2>
        <small>Client: 100 • Production Environment • Live Operational Nodes</small>
    </div>
""", unsafe_with_html=True)

st.sidebar.image("https://sap.com", width=65)
st.sidebar.title("SAP Easy Access")

# SAP Transaction Code Mapping Menu System
tcode_selection = st.sidebar.radio(
    "Select Transaction Node:",
    [
        "📊 Dashboard Overview (Live Monitor)",
        "📥 MIGO - Goods Receipt / Inward (101)",
        "📤 MB1A - Goods Issue / Outward (201)",
        "⚖️ MI07 - Physical Inventory Reconciliation",
        "🔍 MB51 - Document Audit Trail Ledger"
    ]
)

# Active User Sessions Context Emulator
st.sidebar.markdown("---")
current_sap_user = st.sidebar.text_input("Active SAP Terminal User:", value="SAP_USER_MM")

# --- GLOBAL LIVE CONTROLLER ROUTER ---
if "Dashboard Overview" in tcode_selection:
    st.subheader("Global Inventory Executive Overview")
    
    stock_df = fetch_unrestricted_stock_balances()
    conn = get_db_connection()
    total_docs = conn.execute("SELECT COUNT(*) FROM material_ledger").fetchone()[0]
    total_materials = conn.execute("SELECT COUNT(*) FROM material_master").fetchone()[0]
    conn.close()
    
    # High-level SAP Key Performance Indicators
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="Unique Catalog Master SKUs", value=f"{total_materials} active items")
    kpi2.metric(label="Total Logged System Documents", value=f"{total_docs} entries")
    kpi3.metric(label="Total Inventory Holdings Value", value=f"${stock_df['total_value'].sum():,.2f}")
    
    st.write("### <span class='sap-badge'>MMBE</span> Material Stock Balance Valuation Matrix", unsafe_allow_html=True)
    st.dataframe(stock_df, use_container_width=True, hide_index=True)

elif "MIGO" in tcode_selection:
    st.subheader("MIGO — Post Goods Receipt / Inward Execution")
    
    conn = get_db_connection()
    master_df = pd.read_sql_query("SELECT material_id, description FROM material_master", conn)
    conn.close()
    
    with st.form("migo_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            selected_mat = st.selectbox("Material Master ID", options=master_df['material_id'] + " (" + master_df['description'] + ")")
            target_sloc = st.selectbox("Target Storage Location Block", ["SLOC-A1 (General Rack)", "SLOC-B2 (Bulk Floor)", "SLOC-C3 (Cold Storage Zone)"])
        with col2:
            receipt_qty = st.number_input("Inbound Count / Receipt Quantity", min_value=0.01, step=1.0, format="%.2f")
            ref_document = st.text_input("External Reference Document (PO / Invoice Ref)", placeholder="PO-2026-8901")
            
        submit_migo = st.form_submit_button("Execute Post Goods Receipt [Movement Type 101]")
        
        if submit_migo:
            mat_id_parsed = selected_mat.split(" ")[0]
            generated_doc_id = f"MATDOC-101-{int(datetime.now().timestamp())}"
            
            db_conn = get_db_connection()
            db_conn.execute("""
                INSERT INTO material_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                generated_doc_id, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                mat_id_parsed, 
                "101 (Goods Receipt)", 
                receipt_qty, 
                target_sloc.split(" ")[0], 
                "COST-CTR-INBOUND", 
                ref_document if ref_document else "N/A", 
                current_sap_user
            ))
            db_conn.commit()
            db_conn.close()
            
            st.success(f"Transaction Confirmed! SAP Material Document {generated_doc_id} has been recorded into the distributed ledger network.")

elif "MB1A" in tcode_selection:
    st.subheader("MB1A — Goods Issue / Consumption Processing")
    
    stock_df = fetch_unrestricted_stock_balances()
    
    with st.form("mb1a_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            available_materials = stock_df['material_id'].unique() if not stock_df.empty else []
            if len(available_materials) == 0:
                st.warning("No warehouse stock currently exists across any location mapping.")
            selected_mat = st.selectbox("Source Material ID", options=available_materials)
            
            # Dynamically filter valid storage locations for the chosen item
            filtered_slocs = stock_df[stock_df['material_id'] == selected_mat]['storage_location'].unique()
            source_sloc = st.selectbox("Source Storage Location Slot", options=filtered_slocs)
            
        with col2:
