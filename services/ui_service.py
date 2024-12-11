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
            
            logger.info(f"Sheet {sheet_name} data loaded - Shape: {df.shape if df is not None else 'None'}")
            logger.info(f"Columns found: {df.columns.tolist() if df is not None else []}")
            if df is not None and not df.empty:
                logger.info(f"First row values: {df.iloc[0].tolist() if not df.empty else 'No data'}")
                logger.info(f"Second row values: {df.iloc[1].tolist() if len(df) > 1 else 'No second row'}")
                logger.info(f"Second row types: {[type(x).__name__ for x in df.iloc[1]] if len(df) > 1 else 'No second row'}")
                logger.info(f"DataFrame info: {df.info()}")
            
            # Get form fields and formula fields from sheet structure
            logger.info(f"Generating form fields for sheet {sheet_name}")
            form_fields, formula_fields = form_builder_service.get_form_fields(
                df,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            )
            
            if not form_fields and not formula_fields:
                st.warning(f"Could not generate form fields from sheet '{sheet_name}'")
                logger.error(f"No form fields or formula fields generated for sheet {sheet_name}")
                return None
                
            # Store formula fields in session state for use during form submission
            if 'formula_fields' not in st.session_state:
                st.session_state.formula_fields = {}
            st.session_state.formula_fields[sheet_name] = formula_fields
            
            logger.info(f"Generated {len(form_fields)} form fields")
            
            # Render the form with sheet name
            form_data = form_builder_service.render_form(form_fields, sheet_name)
            
            # Add submit button
            if st.button("Submit Entry", type="primary"):
                try:
                    # Find the first empty row in the current sheet
                    entry_range = f"{sheet_name}!A:A"  # Only check column A
                    entry_df = sheets_client.read_spreadsheet(spreadsheet_id, entry_range)
                    
                    # Calculate next available row - start from row 2 (after header)
                    next_row = 2
                    if not entry_df.empty:
                        # Find first empty row
                        mask = entry_df[entry_df.columns[0]].notna()
                        if mask.any():
                            next_row = len(mask[mask]) + 2  # Add 2 to account for header row
                    
                    # Use copy functionality with calculated row
                    # Initialize copy service with the sheets_client parameter
                    copy_service = CopyService(sheets_client)
                    success = copy_service.copy_entry(
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=sheet_name,
                        source_range=f"{sheet_name}!A2:Z2",
                        target_row=int(next_row)
                    )
                    
                    if success:
                        st.success(f"Entry added successfully at row {next_row}")
                        return form_data
                    else:
                        st.error("Failed to add entry")
                        return None
                        
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
        """Copy volunteer entry to a specific row."""
        try:
            logger.info("=" * 60)
            logger.info("COPY OPERATION")
            logger.info("=" * 60)
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Target Row: {target_row}")
            
            source_range = "Volunteers!A2:Z2"
            logger.info(f"Source Range: {source_range}")

            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name="Volunteers",
                source_range=source_range,
                target_row=target_row
            )
            
            if success:
                success_msg = f"✅ Successfully copied to row {target_row} in Volunteers!"
                logger.info(success_msg)
                st.success(success_msg)
            else:
                error_msg = "Failed to copy entry"
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
        """Display test buttons and forms for various functionalities."""
        try:
            # 1. Copy to Selected Row Form
            st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin-bottom: 0.6rem;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">🔄 Copy Function</h3>
                </div>
            """, unsafe_allow_html=True)

            # Get available sheets for selection
            try:
                metadata = copy_service.sheets_client.get_spreadsheet_metadata(spreadsheet_id)
                sheet_names = [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]
                
                # Create sheet selector
                selected_sheet = st.selectbox(
                    "Select Sheet",
                    options=sheet_names,
                    index=sheet_names.index("Volunteers") if "Volunteers" in sheet_names else 0,
                    help="Select the sheet to copy from"
                )
            except Exception as e:
                logger.error(f"Error loading sheet names: {str(e)}")
                st.error("Failed to load sheet names")
                return
            
            # Row selection for the selected sheet
            target_row = st.number_input(
                "Target Row",
                min_value=1,
                value=6,
                step=1,
                help="Select the row number where you want to copy the data"
            )
            
            if st.button("Copy to Selected Row", type="primary", key="test_copy_button"):
                try:
                    success = copy_service.copy_entry(
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=selected_sheet,
                        source_range=f"{selected_sheet}!A2:Z2",
                        target_row=target_row
                    )
                    
                    if success:
                        st.success(f"✅ Successfully copied to row {target_row} in {selected_sheet}!")
                    else:
                        st.error("Failed to copy entry")
                except Exception as e:
                    logger.error(f"Error during copy: {str(e)}")
                    st.error(f"Error: {str(e)}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 2. Cell Updates Form
            st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin: 1rem 0 0.6rem 0;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📝 Cell Updates</h3>
                </div>
            """, unsafe_allow_html=True)
            
            # Sheet name input
            sheet_name = st.text_input("Sheet Name", value="Volunteers", 
                                     help="Enter the name of the sheet to update",
                                     key="cell_updates_sheet_name")
            
            # Container for cell updates
            st.markdown("Enter row, column, and value for each cell to update")
            
            # Create 3 rows of inputs by default
            num_updates = 3
            cell_updates = []
            
            for i in range(num_updates):
                col1, col2, col3 = st.columns(3)
                with col1:
                    row = st.number_input(f"Row #{i+1}", 
                                        min_value=1, 
                                        value=4,
                                        key=f"row_{i}")
                with col2:
                    col = st.number_input(f"Column #{i+1}", 
                                        min_value=1,
                                        value=i+1,
                                        help="1=A, 2=B, etc",
                                        key=f"col_{i}")
                with col3:
                    val = st.text_input(f"Value #{i+1}",
                                      value=f"test{i+1}",
                                      key=f"val_{i}")
                cell_updates.extend([row, col, val])
            
            # Preserve form state in session state
            if 'cell_updates_active' not in st.session_state:
                st.session_state.cell_updates_active = False
                
            if st.button("Test Cell Updates", type="primary", key="test_cell_updates"):
                st.session_state.cell_updates_active = True
                try:
                    from services.spreadsheet_service import SpreadsheetService
                    success = SpreadsheetService.UpdateEntryCells(
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=sheet_name,
                        cell_updates=cell_updates
                    )
                    if success:
                        st.success("✅ Cells updated successfully!")
                    else:
                        st.error("❌ Failed to update cells")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                finally:
                    # Reset state after operation
                    st.session_state.cell_updates_active = False
            
            st.markdown("<br>", unsafe_allow_html=True)
                
        except Exception as e:
            logger.error(f"Error displaying test buttons: {str(e)}")
            st.error("Failed to display test buttons")

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