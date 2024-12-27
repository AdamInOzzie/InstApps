
"""Service for handling CHARTS functionality."""
import logging
import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ChartsService:
    @staticmethod
    def handle_charts(sheet_names: List[str], sheet_id: str, sheets_client) -> None:
        """Handle the CHARTS sheet functionality."""
        try:
            # Show Charts dropdown if CHARTS sheet exists
            if 'CHARTS' in sheet_names:
                try:
                    charts_df = sheets_client.read_sheet_data(sheet_id, 'CHARTS')
                    if not charts_df.empty:
                        # Try both column name variants
                        chart_column = next((col for col in ['ChartName', 'CHARTNAME'] 
                                          if col in charts_df.columns), None)
                        
                        if chart_column:
                            chart_names = charts_df[chart_column].dropna().tolist()
                            if chart_names:
                                st.markdown("### 📊 Chart Selection")
                                selected_chart = st.selectbox(
                                    "Select a chart to view",
                                    options=chart_names,
                                    key='chart_selector'
                                )
                except Exception as e:
                    logger.error(f"Error loading CHARTS: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error handling charts: {str(e)}")
            st.error(f"Error displaying charts: {str(e)}")
