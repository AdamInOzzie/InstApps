"""Service for handling UI components and displays."""
import logging
import streamlit as st
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)

class UIService:
    @staticmethod
    def display_connection_status(status: Dict[str, Any]):
        """Display connection status in the sidebar."""
        with st.sidebar:
            st.subheader("System Status")
            
            st.markdown("**API Connection**")
            if status['connected']:
                st.success("✅ Connected to Google Sheets API")
                st.text("Services: Sheets & Drive APIs")
            else:
                st.error("❌ Not connected to Google Sheets API")
                st.text("Unable to access Google APIs")
            
            st.markdown("**Authentication**")
            if status['authenticated']:
                st.success("✅ Service Account Authenticated")
                st.text("Using Google Service Account")
            else:
                st.error("❌ Authentication failed")
                st.text("Check service account credentials")
            
            st.markdown("**Permissions**")
            st.text("• Spreadsheets (Read/Write)")
            st.text("• Drive Metadata (Read)")
            
            if status['error']:
                st.markdown("**Error Details**")
                st.error(f"{status['error']}")
                st.text("Check logs for more information")
                
            st.divider()

    @staticmethod
    def display_data_quality_report(df: pd.DataFrame):
        """Display data quality information."""
        null_counts = df.isnull().sum()
        has_nulls = null_counts.any()
        
        if has_nulls:
            with st.expander("📊 Data Quality Report"):
                st.warning("Some columns have missing values:")
                for col in df.columns:
                    null_rows = df[df[col].isnull()].index.tolist()
                    if null_rows:
                        percentage = (len(null_rows) / len(df)) * 100
                        st.write(f"- {col}: {len(null_rows)} missing values ({percentage:.1f}%)")
                        st.write(f"  Missing in rows: {', '.join(map(str, null_rows))}")

    @staticmethod
    def display_sheet_data(df: pd.DataFrame):
        """Display sheet data with metrics."""
        if df.empty:
            if not df.columns.empty:
                st.info("ℹ️ This sheet only contains headers")
                st.write("Available columns:", df.columns.tolist())
            else:
                st.info("ℹ️ This sheet is completely empty")
            return

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Rows", df.shape[0])
        with col2:
            st.metric("Total Columns", df.shape[1])
        
        column_configs = {col: st.column_config.Column(
            width="auto"
        ) for col in df.columns}
        
        st.dataframe(
            df,
            use_container_width=True,
            column_config=column_configs,
            hide_index=False
        )
