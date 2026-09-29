import streamlit as st
import pandas as pd
import datetime

# 1. Page Config
st.set_page_config(page_title="My Cloud ERP", layout="wide", page_icon="🏢")

# 2. Master Privacy Password Gate
MASTER_PASSWORD = "admin_erp_2026" # Change this to any password you want!

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Secured Cloud ERP Gateway")
    user_pass = st.text_input("Enter Master Password to Access Your ERP:", type="password")
    if st.button("Unlock System"):
        if user_pass == MASTER_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect Password. Access Denied.")
else:
    # 3. Persistent In-Memory Database Simulation
    if "inventory_data" not in st.session_state:
        st.session_state.inventory_data = pd.DataFrame([
            {"SKU": "A101", "Item": "Raw Materials", "Qty": 500, "Cost ($)": 12.50},
            {"SKU": "B202", "Item": "Finished Goods", "Qty": 120, "Cost ($)": 45.00}
        ])

    # 4. Sidebar Navigation
    st.sidebar.title("🏢 Navigation Panel")
    module = st.sidebar.radio("Select Enterprise Department:", [
        "📊 Control Dashboard", 
        "📦 Inventory Management", 
        "💼 Procurement & Settings"
    ])

    # 5. ERP Modules Logic
    if module == "📊 Control Dashboard":
        st.title("📊 Control Dashboard")
        st.write(f"System status checked on: **{datetime.date.today()}**")
        
        # Live KPI Tickers
        k1, k2 = st.columns(2)
        total_items = st.session_state.inventory_data["Qty"].sum()
        total_value = (st.session_state.inventory_data["Qty"] * st.session_state.inventory_data["Cost ($)"]).sum()
        
        k1.metric("Total Warehouse Units", f"{total_items:,}")
        k2.metric("Total Asset Valuation", f"${total_value:,.2f}")
        
        st.subheader("Current Stock Breakdown")
        st.dataframe(st.session_state.inventory_data, use_container_width=True)

    elif module == "📦 Inventory Management":
        st.title("📦 Live Warehouse Ledger")
        st.write("Modify numbers or row entries below, then save updates.")
        
        # Interactive Cloud Spreadsheet Interface
        updated_df = st.data_editor(st.session_state.inventory_data, num_rows="dynamic", use_container_width=True)
        if st.button("Commit Inventory Changes"):
            st.session_state.inventory_data = updated_df
            st.success("Warehouse data updated successfully across the system!")

    elif module == "💼 Procurement & Settings":
        st.title("💼 Enterprise Management Settings")
        st.info("Your system is running securely behind an active login gate.")
        if st.button("Secure Logout"):
            st.session_state.authenticated = False
            st.rerun()
