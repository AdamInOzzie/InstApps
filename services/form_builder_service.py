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
    def check_entry_form_formula(self, spreadsheet_id: str, sheet_name: str, column: str) -> bool:
        """Check if a cell value is a formula using Google Sheets API for Entry Forms."""
        try:
            cell_range = f"{sheet_name}!{column}2"
            logger.info(f"Checking formula in range: {cell_range}")
            
            # Get the cell data for row 2 (first data row) of the specified column
            client = GoogleSheetsClient()
            result = client.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=[cell_range],
                includeGridData=True,
                fields='sheets.data.rowData.values.userEnteredValue,sheets.data.rowData.values.effectiveValue'
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
            if not rowData:
                logger.debug("No row data found.")
                return False

            values = rowData[0].get('values', [])
            if not values:
                logger.debug("No values found in the specified range.")
                return False

            cell = values[0]
            logger.debug(f"Cell data: {cell}")

            # Check if cell contains a formula by examining userEnteredValue
            if 'userEnteredValue' in cell:
                value = cell['userEnteredValue']
                # If the value starts with '=', it's a formula
                if isinstance(value, dict) and 'stringValue' in value and value['stringValue'].startswith('='):
                    logger.info(f"Found formula in {cell_range}: {value['stringValue']}")
                    return True
            else:
                # If there's no 'formulaValue', check 'userEnteredValue'
                user_value = cell.get('userEnteredValue', {})
                # Handle different types of user-entered values
                if 'stringValue' in user_value:
                    logger.debug(f"Cell {cell_range} contains string: {user_value['stringValue']}")
                elif 'numberValue' in user_value:
                    logger.debug(f"Cell {cell_range} contains number: {user_value['numberValue']}")
                elif 'boolValue' in user_value:
                    logger.debug(f"Cell {cell_range} contains boolean: {user_value['boolValue']}")
                elif 'errorValue' in user_value:
                    logger.debug(f"Cell {cell_range} contains error: {user_value['errorValue']}")
                else:
                    logger.debug(f"Cell {cell_range} is empty or contains unsupported type")
                return False
                
        except Exception as e:
            logger.error(f"Error checking formula for {cell_range}: {str(e)}")
            return False

        logger.debug(f"Formula detection result for {str_value}: {is_formula}")
        return is_formula

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
                    
                    # Check row 2 for formulas if available
                    if len(sheet_data) > 1:
                        row2_value = sheet_data.iloc[1][col] if len(sheet_data) > 1 else None
                        logger.info(f"Checking row 2 value for column {col}: {row2_value}")
                        
                        # Skip if row2 is empty or NaN
                        if pd.isna(row2_value):
                            logger.info(f"Skipping column {col} due to empty row 2")
                            continue
                            
                        # Use different formula detection based on context
                        is_formula = False
                        if spreadsheet_id and sheet_name:  # Entry Form context
                            # Get column letter for API call
                            col_idx = sheet_data.columns.get_loc(col)
                            col_letter = chr(65 + col_idx)  # Convert 0-based index to A, B, C, etc.
                            is_formula = self.check_entry_form_formula(spreadsheet_id, sheet_name, col_letter)
                            if is_formula:
                                logger.info(f"Found formula field {col} at column {col_letter} in Entry Form")
                                formula_fields[col] = "FORMULA"  # Don't store actual formula for Entry Forms
                                continue  # Skip adding this field to form fields
                        else:  # INPUTS form context
                            str_value = str(row2_value)
                            logger.debug(f"Raw value for column {col}: {row2_value}")
                            logger.debug(f"String value for column {col}: {str_value}")
                            is_formula = self.is_formula(str_value)
                            if is_formula:
                                logger.info(f"Found formula field {col}: {str_value}")
                                formula_fields[col] = str_value
                                continue  # Skip adding this field to form fields
                    
                    # For non-formula fields, create form field
                    field_info = {
                        'name': col,
                        'type': 'text',
                        'required': True
                    }
                    
                    # Determine type from sheet format if spreadsheet_id and sheet_name are provided
                    if spreadsheet_id and sheet_name:
                        field_info['type'] = self.get_field_type_from_sheet(
                            spreadsheet_id, 
                            sheet_name, 
                            sheet_data.columns.get_loc(col)
                        )
                    else:
                        # Fall back to existing behavior for INPUTS form
                        if len(sheet_data) > 0:
                            sample_values = sheet_data[col].dropna()
                            if not sample_values.empty:
                                sample_value = sample_values.iloc[0]
                                logger.debug(f"Sample value for {col}: {sample_value}")
                                field_info['type'] = self.get_field_type(sample_value)
                    
                    # Add numeric constraints if we have sample data
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
            return form_fields, formula_fields
            
        except Exception as e:
            logger.error(f"Error generating form fields: {str(e)}")
            return [], {}

    @staticmethod
    def get_column_number(column_index: int) -> str:
        """Return column number (1-based index)."""
        return str(column_index)

    def render_form(self, fields: List[Dict[str, Any]], sheet_name: str = "") -> Dict[str, Any]:
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
                
                # Column reference
                column_number = self.get_column_number(idx)
                field_label = f"{field_name}\n<span style='color: #666; font-size: 0.8em;'>Column {column_number}</span>"
                
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
                else:
                    form_data[field_name] = st.text_input(
                        field_label,
                        value=""
                    )
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
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
                
                # Convert form data to cell updates
                for idx, (field_name, value) in enumerate(form_data.items(), start=1):
                    cell_updates.extend([next_row, idx, str(value)])
                    
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
