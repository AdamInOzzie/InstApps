"""Service for handling UI components and displays."""
import logging
import streamlit as st
import pandas as pd
from services.copy_service import CopyService
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class UIService:
    @staticmethod
    def format_output_value(value_str: str, field_name: str) -> str:
        """Format output values while preserving original formatting."""
        try:
            # Remove any commas from the original string
            original_value = str(value_str).strip()
            
            # If it's already a properly formatted value, return as is
            if original_value.startswith('$') or original_value.endswith('%'):
                return original_value
                
            # Check if it's a currency value (should have $ prefix)
            if "Portfolio" in field_name:
                clean_value = original_value.replace('$', '').replace(',', '')
                try:
                    float_value = float(clean_value)
                    return f"${float_value:,.0f}"
                except ValueError:
                    return original_value
                    
            # Check if it's a percentage/allocation value
            if "Allocation" in field_name or "Rate" in field_name:
                try:
                    clean_value = original_value.replace('%', '').replace('$', '').replace(',', '').strip()
                    float_value = float(clean_value)
                    if float_value <= 1:  # Decimal format (e.g., 0.59)
                        float_value *= 100
                    return f"{float_value:.0f}%"
                except ValueError:
                    return original_value
                    
            return original_value
            
        except Exception as e:
            logger.error(f"Error formatting output value: {str(e)}")
            return value_str

    @staticmethod
    def display_admin_sidebar(status: Dict[str, Any]):
        """Display admin-only information in the sidebar."""
        with st.sidebar:
            st.subheader("Admin Dashboard")
            
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
    def handle_append_entry(spreadsheet_id: str, sheet_name: str, sheets_client, form_builder_service) -> Optional[Dict[str, Any]]:
        """Handle the dynamic form generation and submission for appending entries."""
        try:
            # Read the sheet data to get structure
            range_name = f"{sheet_name}!A1:Z1000"
            logger.info(f"Reading sheet data from {range_name}")
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            if df is None or df.empty:
                st.warning(f"Could not read sheet data from '{sheet_name}'")
                return None

            # Get form fields and formula fields from sheet structure
            logger.info(f"Generating form fields for sheet {sheet_name}")
            form_fields, formula_fields = form_builder_service.get_form_fields(df)
            
            if not form_fields:
                st.warning(f"Could not generate form fields from sheet '{sheet_name}'")
                return None
                
            logger.info(f"Generated {len(form_fields)} form fields")
            
            # Render the form with sheet name
            form_data = form_builder_service.render_form(form_fields, sheet_name)
            logger.info(f"Form data after rendering: {form_data}")
            
            # Add submit button
            if st.button("Submit Entry", type="primary"):
                try:
                    try:
                        # First get the sheet structure
                        metadata = sheets_client.get_spreadsheet_metadata(spreadsheet_id)
                        sheet_found = False
                        template_range = "A2:D2"  # Default to A-D columns
                        
                        for sheet in metadata.get('sheets', []):
                            if sheet['properties']['title'] == sheet_name:
                                sheet_found = True
                                # Use actual column count for range
                                col_count = sheet['properties']['gridProperties']['columnCount']
                                if col_count > 0:
                                    end_col = chr(ord('A') + min(col_count - 1, 3))  # Limit to 4 columns (A-D)
                                    template_range = f"A2:{end_col}2"
                                break
                        
                        if not sheet_found:
                            logger.error(f"Sheet {sheet_name} not found in spreadsheet")
                            st.error("Sheet configuration error")
                            return None
                            
                        # Find the next available row
                        range_check = f"{sheet_name}!A:A"
                        df_check = sheets_client.read_spreadsheet(spreadsheet_id, range_check)
                        
                        next_row = 2  # Default to row 2
                        if df_check is not None and not df_check.empty:
                            # Find last non-empty row
                            mask = df_check.iloc[:, 0].notna()
                            if mask.any():
                                next_row = mask.values.nonzero()[0][-1] + 2
                        
                        logger.info(f"Copying template from {template_range} to row {next_row}")
                        
                        # Copy template row
                        copy_service = CopyService(sheets_client)
                        copy_result = copy_service.copy_entry(
                            spreadsheet_id=spreadsheet_id,
                            sheet_name=sheet_name,
                            source_range=template_range,
                            target_row=next_row
                        )
                        
                        if not copy_result:
                            logger.error("Failed to copy template row")
                            st.error("Failed to copy template row")
                            return None
                            
                    except Exception as e:
                        logger.error(f"Error preparing form submission: {str(e)}")
                        st.error("Error preparing form submission")
                        return None

                    logger.info(f"Successfully copied template to row {next_row}")
                    
                    # Only update non-formula fields after template copy
                    for field in form_fields:
                        field_name = field['name']
                        if field_name in form_data and field_name not in formula_fields:
                            try:
                                # Get the value from form_data
                                value = form_data[field_name]
                                
                                # Get original column index from field definition
                                col_idx = field.get('column_index')
                                if col_idx is not None:
                                    col_letter = chr(65 + col_idx)  # Convert to column letter (A=0, B=1, etc.)
                                    update_range = f"{sheet_name}!{col_letter}{next_row}"
                                    
                                    logger.info(f"Writing field '{field_name}' with value '{value}' to cell {update_range}")
                                    result = sheets_client.write_to_spreadsheet(
                                        spreadsheet_id,
                                        update_range,
                                        [[value]]
                                    )
                                    if result:
                                        logger.info(f"Successfully wrote {field_name} to {update_range}")
                                    else:
                                        logger.error(f"Failed to write {field_name} to {update_range}")
                                        st.error(f"Failed to update {field_name}")
                                else:
                                    logger.warning(f"No column index found for field {field_name}")
                            except Exception as e:
                                logger.error(f"Error writing field {field_name} to sheet: {str(e)}")
                                st.error(f"Failed to update {field_name}")
                                continue

                    logger.info("Successfully updated form fields in copied row")
                    st.success(f"✅ Entry added at row {next_row}")
                    return form_data
                    
                except Exception as e:
                    logger.error(f"Error in form submission: {str(e)}")
                    st.error(f"Error: {str(e)}")
                    return None
            
            # If no submission occurred, return the form data
            return form_data
            
        except Exception as e:
            logger.error(f"Error handling append entry: {str(e)}")
            st.error(f"Error generating form: {str(e)}")
            return None

    @staticmethod
    def copy_volunteer_entry(spreadsheet_id: str, copy_service: CopyService, target_row: int) -> bool:
        """Shared copy functionality for volunteer entries."""
        try:
            logger.info("=" * 60)
            logger.info("COPY OPERATION")
            logger.info("=" * 60)
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Target Row: {target_row}")
            
            source_range = "A2:D2"
            sheet_name = "Volunteers"
            
            logger.info(f"Sheet Name: {sheet_name}")
            logger.info(f"Source Range: {source_range}")
            
            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                source_range=source_range,
                target_row=int(target_row)
            )
            
            if success:
                success_msg = f"✅ Successfully copied to row {target_row}!"
                logger.info(success_msg)
                st.success(success_msg)
            else:
                error_msg = f"Failed to copy to row {target_row}"
                logger.error(error_msg)
                st.error(error_msg)
                
            return success
            
        except Exception as e:
            error_msg = f"Error during copy: {str(e)}"
            logger.error(error_msg)
            st.error(error_msg)
            return False

    @staticmethod
    def display_copy_test_button(spreadsheet_id: str, copy_service: CopyService) -> None:
        """Display test button for copy functionality."""
        try:
            st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin-bottom: 0.6rem;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">🔄 Test Copy Function</h3>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            target_row = st.number_input(
                "Target Row",
                min_value=1,
                value=6,
                step=1,
                help="Select the row number where you want to copy the data"
            )
            
            if st.button("Copy to Selected Row", type="primary", key="test_copy_button"):
                UIService.copy_volunteer_entry(spreadsheet_id, copy_service, target_row)
                
        except Exception as e:
            logger.error(f"Error displaying copy test button: {str(e)}")
            st.error("Failed to display copy test button")

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