"""Service for handling UI components and displays."""
import logging
import streamlit as st
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)

class UIService:
    @staticmethod
    def format_output_value(value_str: str, field_name: str) -> str:
        """Format output values while preserving original formatting.
        
        Args:
            value_str: The original string value from the sheet
            field_name: The name of the field
            
        Returns:
            The formatted string value, preserving original formatting
        """
        try:
            # Remove any commas from the original string
            original_value = str(value_str).strip()
            
            # If it's already a properly formatted value, return as is
            if original_value.startswith('$') or original_value.endswith('%'):
                return original_value
                
            # Check if it's a currency value (should have $ prefix)
            if "Portfolio" in field_name:
                # Add $ prefix if missing
                clean_value = original_value.replace('$', '').replace(',', '')
                try:
                    float_value = float(clean_value)
                    return f"${float_value:,.0f}"  # Preserve commas in large numbers
                except ValueError:
                    return original_value
                    
            # Check if it's a percentage/allocation value
            if "Allocation" in field_name or "Rate" in field_name:
                try:
                    # Convert decimal to percentage if needed
                    clean_value = original_value.replace('%', '').replace('$', '').replace(',', '').strip()
                    float_value = float(clean_value)
                    if float_value <= 1:  # Decimal format (e.g., 0.59)
                        float_value *= 100
                    return f"{float_value:.0f}%"  # Format with no decimal places
                except ValueError:
                    return original_value
                    
            # For all other values, return as is
            return original_value
            
        except Exception as e:
            logger.error(f"Error formatting output value: {str(e)}")
            return value_str  # Return original value if any error occurs

    @staticmethod
    def display_admin_sidebar(status: Dict[str, Any]):
        """Display admin-only information in the sidebar."""
        with st.sidebar:
            st.subheader("Admin Dashboard")
            
            # System Status Section
            st.markdown("### System Status")
            
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
    def handle_append_entry(spreadsheet_id: str, sheet_name: str, sheets_client, form_builder_service) -> dict:
        """Handle the dynamic form generation and submission for appending entries.
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet to append to
            sheets_client: The GoogleSheetsClient instance
            form_builder_service: The FormBuilderService instance
            
        Returns:
            dict: The form data if submitted, None otherwise
        """
        try:
            # Read the sheet data to get structure
            range_name = f"{sheet_name}!A1:Z1000"
            logger.info(f"Reading sheet data from {range_name}")
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            logger.info(f"Sheet {sheet_name} data loaded - Shape: {df.shape if df is not None else 'None'}")
            logger.info(f"Columns found: {df.columns.tolist() if df is not None else []}")
            if df is not None:
                logger.info(f"First row values: {df.iloc[0].tolist() if not df.empty else 'No data'}")
                logger.info(f"DataFrame info: {df.info()}")
            
            # Get form fields from sheet structure
            logger.info(f"Generating form fields for sheet {sheet_name}")
            form_fields = form_builder_service.get_form_fields(df)
            
            if not form_fields:
                st.warning(f"Could not generate form fields from sheet '{sheet_name}'")
                logger.error(f"No form fields generated for sheet {sheet_name}")
                return None
            
            logger.info(f"Generated {len(form_fields)} form fields")
            for field in form_fields:
                logger.debug(f"Field: {field['name']}, Type: {field['type']}")
                
            # Render the form
            form_data = form_builder_service.render_form(form_fields)
            
            # Add submit button
            if st.button("Submit Entry", type="primary"):
                try:
                    success = form_builder_service.append_form_data(
                        spreadsheet_id,
                        sheet_name,
                        form_data,
                        sheets_client
                    )
                    if success:
                        st.success("✅ Entry added successfully!")
                        return form_data
                    else:
                        st.error("Failed to add entry")
                except Exception as e:
                    logger.error(f"Error submitting form: {str(e)}")
                    st.error(f"Error submitting form: {str(e)}")
            
            return form_data if form_data else None
            
        except Exception as e:
            logger.error(f"Error handling append entry: {str(e)}")
            st.error(f"Error generating form: {str(e)}")
            return None

    @staticmethod
    def display_sheet_data(df: pd.DataFrame, sheet_type: str = 'general'):
        """Display sheet data in appropriate format based on sheet type."""
        from services.table_service import TableService
        
        # Add a visual indicator for results section
        st.markdown("""
            <div style="
                background-color: #f0f8ff;
                padding: 0.5rem 0.8rem;
                border-radius: 8px;
                border-left: 5px solid #1E88E5;
                margin-bottom: 0.6rem;
            ">
                <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📊 Results</h3>
            </div>
        """, unsafe_allow_html=True)
        
        try:
            if sheet_type == 'outputs':
                # For OUTPUTS sheet, use static table with hidden headers
                TableService.display_static_table(df, hide_index=True, hide_header=True)
            else:
                # For general sheets, use interactive table
                TableService.display_interactive_table(df, enable_pagination=False, allow_export=True)
        except Exception as e:
            logger.error(f"Error displaying dataframe: {str(e)}")
            st.error("Error displaying data. Please check the data format.")
            # Fallback to basic display
            st.write(df)