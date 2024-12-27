"""Service for handling dynamic form operations."""
import logging
import time
import streamlit as st
from typing import Tuple, Any, Optional, List
import pandas as pd
from utils import GoogleSheetsClient

logger = logging.getLogger(__name__)

class FormService:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client

    def get_input_field_data(self, spreadsheet_id: str) -> List[Tuple[str, Any]]:
        """Get input field data from INPUTS sheet."""
        try:
            inputs_range = "INPUTS!A1:B100"  # Read all rows from 1 onwards
            cell_data = self.sheets_client.read_spreadsheet(spreadsheet_id, inputs_range)
            
            if cell_data.empty:
                logger.warning("No data found in INPUTS sheet")
                return []
            
            fields = []
            # Add debug logging
            logger.debug(f"Raw cell data:\n{cell_data}")
            
            # Process each row in the data
            for sheet_row_num in range(1, len(cell_data) + 1):
                try:
                    # Get row data safely
                    row = cell_data.iloc[sheet_row_num - 1] if sheet_row_num <= len(cell_data) else None
                    if row is None:
                        continue

                    field_name = row.iloc[0]
                    current_value = row.iloc[1]
                    
                    # Only skip if both values are empty
                    if pd.isna(field_name) and pd.isna(current_value):
                        logger.warning(f"Empty row found at row {sheet_row_num}")
                        continue
                        
                    logger.info(f"Successfully read field_name: {field_name}, current_value: {current_value}")
                    fields.append((field_name, current_value))
                except Exception as e:
                    logger.error(f"Error accessing values for row {sheet_row_num}: {str(e)}")
                    continue
            
            logger.info(f"Total fields processed: {len(fields)}")
            return fields
            
        except Exception as e:
            logger.error(f"Error reading input field data: {str(e)}")
            raise

    def process_input_value(self, value: Any) -> Tuple[float, str]:
        """Process input value and return numeric value and display format."""
        try:
            if isinstance(value, str) and '%' in value:
                numeric_value = float(value.strip('%')) / 100
                display_value = f"{numeric_value * 100:.2f}%"
                return numeric_value, display_value
            elif isinstance(value, (int, float)) or (
                isinstance(value, str) and value.replace('.', '').isdigit()
            ):
                numeric_value = float(value)
                # Check if this field should be displayed as percentage
                if numeric_value <= 1 and "rate" in str(value).lower():
                    display_value = f"{numeric_value * 100:.2f}%"  # Keep percentages at 2 decimal places
                elif numeric_value < 10:
                    display_value = f"{numeric_value:.3f}"  # 3 decimal places for values under 10
                else:
                    display_value = f"{numeric_value:.2f}"  # 2 decimal places for larger values
                return numeric_value, display_value
            else:
                return None, str(value)
        except ValueError as e:
            logger.error(f"Error processing input value: {str(e)}")
            raise

    def handle_inputs_sheet(self, selected_sheet_id: str) -> bool:
        """Handle the INPUTS sheet form display and processing."""
        try:
            fields = self.get_input_field_data(selected_sheet_id)
            
            if not fields:
                st.warning("No data found in INPUTS sheet. Please ensure the sheet has data.")
                return False
            
            # Create two columns for Inputs dropdown and button
            col1, col2 = st.columns([4, 1])
            
            with col1:
                display_choice = st.selectbox(
                    "Inputs",
                    options=["Display Inputs", "Hide Inputs"],
                    key="inputs_selector",
                    label_visibility="collapsed"
                )
            
            with col2:
                st.button("Update", key="display_inputs_btn")

            def create_callback(row):
                def callback():
                    actual_row = row
                    logger.info("\n" + "="*80)
                    logger.info(f"CALLBACK TRIGGERED for row {actual_row} (sheet row {actual_row})")
                    logger.info("="*80 + "\n")
                    try:
                        input_key = f"input_{row}"
                        logger.info(f"Processing callback for input {input_key} (sheet row {actual_row})")
                        logger.info(f"All session state keys: {list(st.session_state.keys())}")
                        logger.info(f"Current session state for {input_key}: {st.session_state.get(input_key)}")
                        
                        if input_key not in st.session_state:
                            logger.error(f"Session state key {input_key} not found")
                            return
                            
                        value = st.session_state[input_key]
                        logger.info(f"Raw input value retrieved: {value} (type: {type(value)})")
                        
                        from services.spreadsheet_service import SpreadsheetService
                        spreadsheet_service = SpreadsheetService(self.sheets_client)
                        success = spreadsheet_service.update_input_cell(
                            selected_sheet_id,
                            str(value),
                            row
                        )
                        
                        if success:
                            logger.info(f"✅ Successfully updated cell B{row} with value {value}")
                            time.sleep(0.5)
                            st.success("Updated successfully")
                        else:
                            logger.error(f"❌ Failed to update cell B{row}")
                            st.error("Failed to update value")
                            
                    except Exception as e:
                        logger.error(f"Error in callback: {str(e)}")
                        st.error(f"Error updating field: {str(e)}")
                return callback

            if display_choice == "Display Inputs":
                for row_idx, (field_name, current_value) in enumerate(fields, start=2):
                    numeric_value, display_value = self.process_input_value(current_value)
                    
                    if numeric_value is not None:
                        step_size = 0.01 if isinstance(display_value, str) and '%' in display_value or numeric_value < 10 else 1.0
                        input_key = f"input_numeric_{row_idx}"
                        callback_fn = create_callback(row_idx)
                        st.session_state[f"callback_{input_key}"] = callback_fn
                        
                        st.number_input(
                            field_name,
                            value=numeric_value,
                            format="%.3f" if numeric_value < 10 else "%.2f",
                            step=step_size,
                            key=input_key,
                            on_change=st.session_state[f"callback_{input_key}"],
                            help=f"Column {row_idx}"
                        )
                    else:
                        input_key = f"input_text_{row_idx}"
                        callback_fn = create_callback(row_idx)
                        st.session_state[f"callback_{input_key}"] = callback_fn
                        
                        st.text_input(
                            field_name,
                            value=str(current_value),
                            key=input_key,
                            on_change=st.session_state[f"callback_{input_key}"]
                        )
                        def callback():
                            actual_row = row
                            logger.info("\n" + "="*80)
                            logger.info(f"CALLBACK TRIGGERED for row {actual_row} (sheet row {actual_row})")
                            logger.info("="*80 + "\n")
                            try:
                                input_key = f"input_{row}"
                                logger.info(f"Processing callback for input {input_key} (sheet row {actual_row})")
                                logger.info(f"All session state keys: {list(st.session_state.keys())}")
                                logger.info(f"Current session state for {input_key}: {st.session_state.get(input_key)}")
                                
                                if input_key not in st.session_state:
                                    logger.error(f"Session state key {input_key} not found")
                                    return
                                    
                                value = st.session_state[input_key]
                                logger.info(f"Raw input value retrieved: {value} (type: {type(value)})")
                                
                                current_fields = self.get_input_field_data(selected_sheet_id)
                                current_field_name = None
                                current_field_value = None
                                
                                for field_name, field_value in current_fields:
                                    if isinstance(field_value, str):
                                        if field_value.endswith('%'):
                                            current_field_value = field_value
                                            current_field_name = field_name
                                            break
                                        elif field_value.startswith('$'):
                                            current_field_value = field_value
                                            current_field_name = field_name
                                            break
                                
                                if current_field_value:
                                    if '%' in current_field_value:
                                        formatted_value = f"{float(value):.4f}"
                                    elif current_field_value.startswith('$'):
                                        clean_value = str(value).replace('$', '').replace(',', '')
                                        formatted_value = f"{float(clean_value):.2f}"
                                    else:
                                        formatted_value = str(value)
                                else:
                                    formatted_value = str(value)
                                    
                                from services.spreadsheet_service import SpreadsheetService
                                spreadsheet_service = SpreadsheetService(self.sheets_client)
                                success = spreadsheet_service.update_input_cell(
                                    selected_sheet_id,
                                    formatted_value,
                                    row
                                )
                                
                                if success:
                                    logger.info(f"✅ Successfully updated cell B{row} with value {formatted_value}")
                                    time.sleep(0.5)
                                    st.success(f"Updated {current_field_name}")
                                else:
                                    logger.error(f"❌ Failed to update cell B{row}")
                                    st.error(f"Failed to update {current_field_name}")
                                    
                            except Exception as e:
                                logger.error(f"Error in callback: {str(e)}")
                                st.error(f"Error updating field: {str(e)}")
                        return callback

                    format_str = "%.2f" if numeric_value >= 10 else "%.3f"
                    if isinstance(display_value, str) and '%' in display_value:
                        format_str = "%.2f"
                    
                    input_key = f"input_{row_idx}"
                    callback_fn = create_callback(row_idx)
                    st.session_state[f"callback_{input_key}"] = callback_fn
                    
                    st.number_input(
                        field_name,
                        value=numeric_value,
                        format=format_str,
                        step=step_size,
                        key=input_key,
                        on_change=st.session_state[f"callback_{input_key}"],
                        help=f"Column {row_idx}"
                    )
                else:
                    input_key = f"input_{row_idx}"
                    st.text_input(
                        field_name,
                        value=str(current_value),
                        key=input_key,
                        on_change=create_callback(row_idx)
                    )
            return True
            
        except Exception as e:
            logger.error(f"Error processing INPUTS sheet: {str(e)}")
            st.error(f"⚠️ Failed to process INPUTS sheet: {str(e)}")
            return False