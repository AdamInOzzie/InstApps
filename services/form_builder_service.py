"""Service for building and handling dynamic forms from Google Sheets."""
import logging
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd
import streamlit as st
from services.copy_service import CopyService
from utils.google_sheets import GoogleSheetsClient

logger = logging.getLogger(__name__)

class FormBuilderService:
    @staticmethod
    def is_formula(value: Any) -> bool:
        """Check if a cell value is a formula."""
        if pd.isna(value):
            return False
        str_value = str(value).strip()
        
        # Log the value being checked
        logger.debug(f"Checking if value is formula: {str_value}")
        
        # First check if it starts with =
        if not str_value.startswith('='):
            return False
            
        # Check for any formula patterns
        formula_patterns = [
            # Basic operators
            '+', '-', '*', '/', '(', ')',
            # Common functions
            'SUM', 'AVERAGE', 'COUNT', 'IF', 'AND', 'OR',
            # Lookup functions
            'VLOOKUP', 'INDEX', 'MATCH',
            # Text functions
            'CONCATENATE', 'LEFT', 'RIGHT', 'MID',
            # Date functions
            'DATE', 'TODAY', 'NOW', 'EOMONTH', 'WEEKDAY',
            'EDATE', 'DAY', 'MONTH', 'YEAR', 'WORKDAY',
            # Special cases for date calculations
            'DATEVALUE', '+7', '-7', '+14', '-14'  # Common date offset patterns
        ]
        
        is_formula = any(op in str_value.upper() for op in formula_patterns)
        return is_formula

    def check_entry_form_formula(self, spreadsheet_id: str, sheet_name: str, column: str) -> bool:
        """Check if a cell value is a formula using Google Sheets API for Entry Forms."""
        try:
            cell_range = f"{sheet_name}!{column}2"
            logger.info(f"Checking formula in range: {cell_range}")
            
            # Get the cell data with specific formula information
            client = GoogleSheetsClient()
            result = client.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=[cell_range],
                includeGridData=True
            ).execute()

            # Extract the cell data
            sheets = result.get('sheets', [])
            if not sheets:
                logger.debug("No sheets found.")
                return False

            data = sheets[0].get('data', [])
            if not data:
                logger.debug("No data found in the sheet.")
                return False

            rowData = data[0].get('rowData', [])
            if not rowData or not rowData[0].get('values'):
                logger.debug("No row data or values found.")
                return False

            cell = rowData[0]['values'][0]
            logger.debug(f"Raw cell data: {cell}")

            # Check for formula in userEnteredValue
            if 'userEnteredValue' in cell:
                value = cell['userEnteredValue']
                if isinstance(value, dict) and 'formulaValue' in value:
                    formula = value['formulaValue']
                    logger.info(f"Found formula in {cell_range}: {formula}")
                    return True
                elif isinstance(value, dict) and 'stringValue' in value and value['stringValue'].startswith('='):
                    logger.info(f"Found formula string in {cell_range}: {value['stringValue']}")
                    return True

            logger.debug(f"No formula found in {cell_range}")
            return False
                
        except Exception as e:
            logger.error(f"Error checking formula for {cell_range}: {str(e)}")
            return False

    @staticmethod
    def get_field_type(value: Any) -> str:
        """Determine the appropriate field type based on the sample value."""
        if pd.isna(value):
            return 'text'
            
        if isinstance(value, (int, float)):
            return 'number'
        elif isinstance(value, bool):
            return 'checkbox'
        elif isinstance(value, pd.Timestamp):
            return 'date'
        else:
            str_value = str(value).strip()
            # Check for date-like strings (e.g., "2024-12-11")
            if str_value and len(str_value.split('-')) == 3:
                try:
                    pd.to_datetime(str_value)
                    return 'date'
                except:
                    pass
            if str_value.endswith('%'):
                return 'percentage'
            elif str_value.startswith('$'):
                return 'currency'
            return 'text'

    def get_field_type_from_sheet(self, spreadsheet_id: str, sheet_name: str, column_index: int) -> str:
        """Determine field type using Google Sheets API format information."""
        try:
            # Get the format information for the first data row (row 2)
            client = GoogleSheetsClient()
            sheet = client.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=[f"{sheet_name}!{chr(65 + column_index)}2"],
                includeGridData=True
            ).execute()

            # Extract the cell data
            if (sheet.get('sheets') and sheet['sheets'][0].get('data') and 
                sheet['sheets'][0]['data'][0].get('rowData') and
                sheet['sheets'][0]['data'][0]['rowData'][0].get('values')):
                
                cell_data = sheet['sheets'][0]['data'][0]['rowData'][0]['values'][0]
                
                # Check if it has an effectiveFormat and numberFormat
                if ('effectiveFormat' in cell_data and 
                    'numberFormat' in cell_data['effectiveFormat']):
                    number_format = cell_data['effectiveFormat']['numberFormat']
                    if number_format['type'] in ('DATE', 'DATE_TIME'):
                        return 'date'
                    elif number_format['type'] == 'PERCENT':
                        return 'percentage'
                    elif number_format['type'] == 'CURRENCY':
                        return 'currency'
                    elif number_format['type'] == 'NUMBER':
                        return 'number'
            
            return 'text'  # Default to text if no specific format is found
            
        except Exception as e:
            logger.error(f"Error getting field type from sheet: {str(e)}")
            return 'text'  # Default to text on error

    def get_form_fields(self, sheet_data: pd.DataFrame, spreadsheet_id: str = None, sheet_name: str = None) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Extract form fields from sheet headers and check row 2 for formulas.
        
        Args:
            sheet_data: DataFrame containing the sheet data
            spreadsheet_id: Optional spreadsheet ID for getting format information
            sheet_name: Optional sheet name for getting format information
            
        Returns:
            Tuple of (form field definitions, formula fields dictionary)
            where formula fields dictionary maps column names to their formula strings
        """
        # Create cache key for this sheet
        cache_key = f"form_fields_{spreadsheet_id}_{sheet_name}" if spreadsheet_id and sheet_name else None
        if cache_key and cache_key in st.session_state:
            return st.session_state[cache_key]
        try:
            # Add debug logging
            logger.debug(f"Raw cell data:\n{sheet_data}")
            
            if sheet_data is None:
                logger.warning("Sheet data is None")
                return [], {}
                
            if sheet_data.empty:
                logger.warning("Sheet is completely empty")
                return [], {}

            logger.info(f"Processing {len(sheet_data.columns)} columns from header row")
            form_fields = []
            formula_fields = {}
            
            # Process each column header as a field
            for col in sheet_data.columns:
                try:
                    # Skip if column header is empty or NaN
                    if pd.isna(col) or str(col).strip() == '':
                        logger.info(f"Skipping empty column header")
                        continue
                        
                    logger.info(f"Processing header field: {col}")
                    
                    # Check for formulas in Entry Form context
                    if spreadsheet_id and sheet_name:
                        try:
                            col_idx = sheet_data.columns.get_loc(col)
                            col_letter = chr(65 + col_idx)
                            logger.info(f"Checking for formula in column {col} (letter: {col_letter})")
                            
                            is_formula = self.check_entry_form_formula(spreadsheet_id, sheet_name, col_letter)
                            if is_formula:
                                logger.info(f"Found formula field {col} at column {col_letter} in Entry Form")
                                formula_fields[col] = "FORMULA"
                                logger.info(f"Skipping form field generation for formula column: {col}")
                                continue
                            else:
                                logger.info(f"No formula found in column {col}, will create form field")
                        except Exception as e:
                            logger.error(f"Error checking formula for column {col}: {str(e)}")
                            # If we can't determine formula status, skip this field for safety
                            continue
                    
                    # For INPUTS form context, check row 2 values
                    elif len(sheet_data) > 1:
                        row2_value = sheet_data.iloc[1][col]
                        if not pd.isna(row2_value):
                            row2_str = str(row2_value)
                            if self.is_formula(row2_str):
                                logger.info(f"Found formula field {col}: {row2_str}")
                                formula_fields[col] = row2_str
                                continue
                    
                    # Create form field for non-formula fields with column position
                    col_idx = sheet_data.columns.get_loc(col)
                    field_info = {
                        'name': col,
                        'type': 'text',
                        'required': True,
                        'column_index': col_idx  # Store the actual column index
                    }
                    logger.info(f"Field {col} will use column_index {col_idx} (column {chr(65 + col_idx)})")
                    
                    # Determine field type
                    if spreadsheet_id and sheet_name:
                        field_info['type'] = self.get_field_type_from_sheet(
                            spreadsheet_id, 
                            sheet_name, 
                            sheet_data.columns.get_loc(col)
                        )
                    elif len(sheet_data) > 0:
                        sample_values = sheet_data[col].dropna()
                        if not sample_values.empty:
                            sample_value = sample_values.iloc[0]
                            field_info['type'] = self.get_field_type(sample_value)
                    
                    # Add numeric constraints if applicable
                    if field_info['type'] == 'number' and len(sheet_data) > 0:
                        try:
                            numeric_values = pd.to_numeric(sheet_data[col], errors='coerce').dropna()
                            if not numeric_values.empty:
                                field_info['min_value'] = float(numeric_values.min())
                                field_info['max_value'] = float(numeric_values.max())
                        except Exception as e:
                            logger.warning(f"Could not determine numeric constraints for {col}: {e}")
                    
                    form_fields.append(field_info)
                    logger.info(f"Added field '{col}' of type '{field_info['type']}'")
                    
                except Exception as e:
                    logger.error(f"Error processing field {col}: {str(e)}")
                    continue
            
            logger.info(f"Generated {len(form_fields)} form fields and {len(formula_fields)} formula fields")
            # Cache the results
            if cache_key:
                st.session_state[cache_key] = (form_fields, formula_fields)
            return form_fields, formula_fields
            
        except Exception as e:
            logger.error(f"Error generating form fields: {str(e)}")
            return [], {}

    @staticmethod
    def get_column_number(column_index: int) -> str:
        """Return column number (1-based index)."""
        return str(column_index)

    def render_form(self, fields: List[Dict[str, Any]], sheet_name: str = "", spreadsheet_id: str = None, sheets_client: GoogleSheetsClient = None) -> Dict[str, Any]:
        """Render a dynamic form based on field definitions."""
        form_data = {}
        
        if not fields:  # Don't show anything if no fields are provided
            return form_data
            
        st.markdown(f"""
            <div style="
                background-color: #f0f8ff;
                padding: 0.5rem 0.8rem;
                border-radius: 8px;
                border-left: 5px solid #1E88E5;
                margin-bottom: 0.6rem;
            ">
                <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📝 New Entry for {sheet_name}</h3>
            </div>
        """, unsafe_allow_html=True)
        
        for idx, field in enumerate(fields, start=1):
            try:
                field_name = field['name']
                field_type = field['type']
                
                # Just use field name as label
                field_label = field_name
                
                if field_type == 'number':
                    step_size = 0.01 if float(field.get('min_value', 0)) < 10 else 1.0
                    form_data[field_name] = st.number_input(
                        field_label,
                        min_value=field.get('min_value', None),
                        max_value=field.get('max_value', None),
                        step=step_size,
                        value=0.0
                    )
                elif field_type == 'date':
                    form_data[field_name] = st.date_input(
                        field_label
                    )
                elif field_type == 'checkbox':
                    form_data[field_name] = st.checkbox(
                        field_label
                    )
                elif field_type == 'percentage':
                    value = st.number_input(
                        f"{field_label} (%)",
                        step=0.1,
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0
                    )
                    form_data[field_name] = f"{value}%"
                elif field_type == 'currency':
                    value = st.number_input(
                        field_label,
                        step=0.01,
                        min_value=0.0,
                        value=0.0
                    )
                    form_data[field_name] = f"${value:.2f}"
                elif field_type == 'text':
                    if field_name == 'Name' and sheet_name != 'USERS':
                        try:
                            # Check for USERS sheet
                            users_df = sheets_client.read_spreadsheet(spreadsheet_id, 'USERS!A:A')
                            if not users_df.empty:
                                users = users_df['Name'].dropna().tolist()
                                if users:
                                    form_data[field_name] = st.selectbox(
                                        field_label,
                                        options=users,
                                        key=f"{sheet_name}_name_select"
                                    )
                                    continue
                        except Exception as e:
                            logger.error(f"Error loading users: {str(e)}")
                    
                    # Default to text input if no users or error
                    form_data[field_name] = st.text_input(
                        field_label,
                        value=""
                    )
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
        button_id = sheet_name.rstrip('s')
        if st.button(f"Submit {button_id}", type="primary", key=f"submit_{button_id}"):
            # Add your submit logic here
            pass
        return form_data

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data as a new row in the sheet by copying row 2 as template."""
        try:
            logger.info(f"Starting form data append process for sheet: {sheet_name}")
            
            # Get range for column A to find next available row
            range_name = f"{sheet_name}!A:A"
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            # Calculate next available row
            next_row = 2  # Start from row 2 (after header)
            if not df.empty:
                # Find last non-empty row and add 1
                mask = df.iloc[:, 0].notna()
                if mask.any():
                    next_row = mask.values.nonzero()[0][-1] + 3  # +2 for header and +1 for next row
            
            logger.info(f"Calculated next available row: {next_row}")
            
            # 1. Copy template row
            copy_service = CopyService(sheets_client)
            source_range = f"{sheet_name}!A2:Z2"
            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                source_range=source_range,
                target_row=next_row
            )
            
            if not success:
                logger.error("Failed to copy template row")
                return False
                
            # 2. Update cells with form data
            try:
                from services.spreadsheet_service import SpreadsheetService
                cell_updates = []
                
                # Convert form data to cell updates using stored column indices
                for field_name, value in form_data.items():
                    # Find the field info to get the column index
                    field_info = next((f for f in fields if f['name'] == field_name), None)
                    if field_info:
                        # Column indices are 0-based, but need to be 1-based for the update
                        column_index = field_info['column_index'] + 1
                        cell_updates.extend([next_row, column_index, str(value)])
                    
                # Execute cell updates
                update_success = SpreadsheetService.UpdateEntryCells(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    cell_updates=cell_updates
                )
                
                if update_success:
                    logger.info(f"Successfully updated cells in row {next_row}")
                    return True
                else:
                    logger.error(f"Failed to update cells in row {next_row}")
                    return False
                    
            except Exception as cell_error:
                logger.error(f"Error updating cells: {str(cell_error)}")
                return False
                
        except Exception as e:
            logger.error(f"Error in append_form_data: {str(e)}")
            logger.exception("Full traceback:")
            return False