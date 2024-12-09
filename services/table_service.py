"""Service for handling table displays from Google Sheets data."""
import logging
import streamlit as st
import pandas as pd
from typing import Optional, List
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

logger = logging.getLogger(__name__)

class TableService:
    @staticmethod
    def format_numeric_value(value: float, format_type: str = 'number', decimals: int = 0) -> str:
        """Format numeric values based on type."""
        if pd.isnull(value):
            return ''
            
        try:
            # Convert string percentage to float if needed
            if isinstance(value, str) and '%' in value:
                value = float(value.replace('%', '')) / 100
                
            if format_type == 'currency':
                return f"${value:,.{decimals}f}"
            elif format_type == 'percent':
                # If value is already in percentage form (e.g., 0.59 for 59%)
                if value <= 1:
                    value = value * 100
                return f"{value:.{decimals}f}%"
            else:
                return f"{value:,.{decimals}f}"
        except Exception as e:
            logger.error(f"Error formatting value {value}: {str(e)}")
            return str(value)

    @staticmethod
    def prepare_display_dataframe(df: pd.DataFrame, is_outputs: bool = False) -> pd.DataFrame:
        """Prepare dataframe for display by handling formatting."""
        # Create a copy for display
        display_df = df.copy()
        
        # For each column, check if there's a formatted version
        for col in df.columns:
            if not col.endswith('_formatted'):
                formatted_col = f"{col}_formatted"
                if formatted_col in df.columns:
                    # Use the preserved formatting from Google Sheets
                    display_df[col] = df[formatted_col]
                elif display_df[col].dtype in ['float64', 'float32'] or (
                    display_df[col].dtype == 'object' and 
                    display_df[col].astype(str).str.contains(r'[\d\.]+%?', na=False).any()
                ):
                    # Use preserved formatting from Google Sheets if available
                    formatted_col = f"{col}_formatted"
                    if formatted_col in df.columns:
                        display_df[col] = df[formatted_col]
                    else:
                        # Handle numeric values without preserved formatting
                        def format_value(x):
                            if pd.isnull(x):
                                return ''
                            if isinstance(x, str):
                                # Already formatted string
                                if '%' in x or '$' in x:
                                    return x
                                try:
                                    x = float(x.replace(',', ''))
                                except ValueError:
                                    return x
                            # Default numeric formatting if no preserved format
                            if isinstance(x, (int, float)):
                                return f"{x:,.2f}"
                            return str(x)
                        display_df[col] = display_df[col].apply(format_value)
                            
                    display_df[col] = display_df[col].apply(format_value)
        
        # Filter out the _formatted columns from final display
        display_columns = [col for col in display_df.columns if not col.endswith('_formatted')]
        return display_df[display_columns]

    @staticmethod
    def display_static_table(df: pd.DataFrame, hide_index: bool = True, hide_header: bool = False):
        """Display a static table with custom styling."""
        if df.empty:
            if not df.columns.empty:
                st.info("ℹ️ This sheet only contains headers")
                st.write("Available columns:", df.columns.tolist())
            else:
                st.info("ℹ️ This sheet is completely empty")
            return

        # Add custom CSS for table styling
        st.markdown("""
            <style>
                .stTable {
                    background-color: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .stTable td {
                    font-size: 1.1rem;
                    padding: 0.75rem 1rem !important;
                    border-bottom: 1px solid #f0f0f0;
                }
                .stTable tr:last-child td {
                    border-bottom: none;
                }
                /* Conditional styling for index and header */
                .stTable th {
                    display: none !important;
                }
                table.dataframe thead {
                    display: none !important;
                }
                .index_column {
                    display: none !important;
                }
            </style>
        """, unsafe_allow_html=True)
        
        display_df = TableService.prepare_display_dataframe(df, is_outputs=hide_header)
        if hide_index:
            display_df = display_df.reset_index(drop=True)
        st.table(display_df)

    @staticmethod
    def display_interactive_table(df: pd.DataFrame, 
                                enable_pagination: bool = False,
                                page_size: int = 10,
                                allow_export: bool = True):
        """Display an interactive table with filtering and sorting."""
        if df.empty:
            st.info("ℹ️ No data available")
            return

        display_df = TableService.prepare_display_dataframe(df)
        
        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_default_column(
            resizable=True,
            filterable=True,
            sorteable=True,
            editable=False
        )
        
        # Configure grid options
        grid_options = {
            'domLayout': 'normal',
            'enableRangeSelection': True,
            'enableCellTextSelection': True,
            'suppressFieldDotNotation': True,
            'rowHeight': 35,
            'headerHeight': 35
        }
        
        if enable_pagination:
            grid_options['pagination'] = True
            grid_options['paginationPageSize'] = page_size
            
        gb.configure_grid_options(**grid_options)
        
        # Display the grid
        AgGrid(
            display_df,
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            allow_unsafe_jscode=True,
            theme='streamlit'
        )
        
        # Add export functionality
        if allow_export:
            if st.button('Export to CSV'):
                csv = df.to_csv(index=False)
                st.download_button(
                    "Download CSV",
                    csv,
                    "data.csv",
                    "text/csv",
                    key='download-csv'
                )
