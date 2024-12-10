"""Service for building and handling dynamic forms from Google Sheets."""
import logging
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd
import streamlit as st

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
            if str_value.endswith('%'):
                return 'percentage'
            elif str_value.startswith('$'):
                return 'currency'
            return 'text'

    def get_form_fields(self, sheet_data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract form fields from sheet headers and check row 2 for formulas.
        
        Args:
            sheet_data: DataFrame containing the sheet data
            
        Returns:
            List of form field definitions with formula detection
        """
        try:
            # Add debug logging
            logger.debug(f"Raw cell data:\n{sheet_data}")
            
            if sheet_data is None:
                logger.warning("Sheet data is None")
                return []
                
            if sheet_data.empty:
                if not sheet_data.columns.empty:
                    # Sheet has headers but no data
                    logger.info("Sheet has headers but no data rows")
                    form_fields = []
                    for col in sheet_data.columns:
                        form_fields.append({
                            'name': col,
                            'type': 'text',
                            'required': True
                        })
                    return form_fields
                logger.warning("Sheet is completely empty")
                return []

            logger.info(f"Processing {len(sheet_data.columns)} columns from header row")
            form_fields = []
            
            # Process each column header as a field
            for col in sheet_data.columns:
                try:
                    logger.info(f"Processing header field: {col}")
                    
                    # Always create a text field by default for each column header
                    field_info = {
                        'name': col,
                        'type': 'text',
                        'required': True,
                        'is_formula': False,
                        'formula_value': None
                    }
                    
                    # Check row 2 for formulas if available
                    if len(sheet_data) > 1:  # Make sure we have at least 2 rows
                        row2_value = sheet_data.iloc[1][col] if len(sheet_data) > 1 else None
                        logger.info(f"Checking row 2 value for column {col}: {row2_value}")
                        
                        # Convert to string for formula checking
                        if row2_value is not None:
                            str_value = str(row2_value)
                            logger.debug(f"Raw value for column {col}: {row2_value}")
                            logger.debug(f"String value for column {col}: {str_value}")
                            is_formula = self.is_formula(str_value)
                            logger.info(f"Column {col} formula check result: {is_formula}")
                            
                            if is_formula:
                                logger.info(f"Skipping formula field {col}: {str_value}")
                                continue  # Skip adding this field entirely since it's a formula
                    
                    # For non-formula fields, determine type from data
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
            
            logger.info(f"Generated {len(form_fields)} form fields from header row")
            return form_fields
            
        except Exception as e:
            logger.error(f"Error generating form fields: {str(e)}")
            return []

    def render_form(self, fields: List[Dict[str, Any]], sheet_name: str = "") -> Dict[str, Any]:
        """Render a dynamic form based on field definitions, handling formula fields differently."""
        form_data = {}
        
        if not fields:  # Don't show anything if no fields are provided
            return form_data
            
        # Track which fields are formulas for later use
        if 'formula_fields' not in st.session_state:
            st.session_state.formula_fields = {}
            
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
        
        for field in fields:
            try:
                field_name = field['name']
                field_type = field['type']
                
                if field_type == 'number':
                    step_size = 0.01 if float(field.get('min_value', 0)) < 10 else 1.0
                    form_data[field_name] = st.number_input(
                        field_name,
                        min_value=field.get('min_value', None),
                        max_value=field.get('max_value', None),
                        step=step_size,
                        value=0.0
                    )
                elif field_type == 'date':
                    form_data[field_name] = st.date_input(field_name)
                elif field_type == 'checkbox':
                    form_data[field_name] = st.checkbox(field_name)
                elif field_type == 'percentage':
                    value = st.number_input(
                        f"{field_name} (%)",
                        step=0.1,
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0
                    )
                    form_data[field_name] = f"{value}%"
                elif field_type == 'currency':
                    value = st.number_input(
                        field_name,
                        step=0.01,
                        min_value=0.0,
                        value=0.0
                    )
                    form_data[field_name] = f"${value:.2f}"
                else:
                    form_data[field_name] = st.text_input(field_name, value="")
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
        return form_data

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data as a new row in the sheet, copying row 2 as template with proper formula adjustments."""
        try:
            logger.info("="*50)
            logger.info("FORM SUBMISSION DETAILS")
            # Validate form data
            if not form_data:
                logger.error("Form data is empty")
                return False
            logger.info(f"Form data validation passed with {len(form_data)} fields")

            logger.info("="*50)
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Sheet Name: {sheet_name}")
            logger.info(f"Form Data: {form_data}")
            
            # Step 1: Get metadata to determine sheet ID
            metadata = sheets_client.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in metadata.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
                    
            if not sheet_id:
                logger.error(f"Could not find sheet ID for {sheet_name}")
                return False

            logger.info(f"Found sheet ID: {sheet_id}")

            # Step 2: Get current sheet data to determine next row
            data_range = f"{sheet_name}!A1:Z1000"
            result = sheets_client.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=data_range
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.error("No data found in sheet")
                return False
                
            next_row = len(values) + 1
            logger.info(f"Next row will be: {next_row}")

            # Step 3: Get headers from first row
            headers = values[0]
            logger.info(f"Found headers: {headers}")

            # Get the template row (row 2) with formulas
            template_row_range = f"{sheet_name}!A2:Z2"
            logger.info(f"Fetching template row from range: {template_row_range}")
            template_result = sheets_client.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=template_row_range,
                valueRenderOption='FORMULA'
            ).execute()
            
            template_values = template_result.get('values', [[]])[0]
            logger.info(f"Template row values: {template_values}")

            # Prepare new row values with form data and adjusted formulas
            new_row_values = []
            for i, header in enumerate(headers):
                if i < len(template_values) and str(template_values[i]).startswith('='):
                    # It's a formula - adjust row references
                    formula = template_values[i]
                    adjusted_formula = formula.replace(f'2', str(next_row))
                    logger.info(f"Adjusted formula for {header}: {adjusted_formula}")
                    new_row_values.append(adjusted_formula)
                elif header in form_data:
                    # It's a form field - use the submitted value
                    value = form_data[header]
                    logger.info(f"Using form value for {header}: {value}")
                    new_row_values.append(value)
                else:
                    # Use empty string for any remaining fields
                    logger.info(f"No value for {header}, using empty string")
                    new_row_values.append('')

            logger.info(f"Final new row values: {new_row_values}")
            
            # Prepare final values for the update
            update_range = f"{sheet_name}!A{next_row}:{chr(65 + len(headers) - 1)}{next_row}"
            logger.info(f"Updating range: {update_range}")
            
            try:
                # Log the API request details
                logger.info("="*50)
                logger.info("GOOGLE SHEETS API REQUEST DETAILS")
                logger.info("="*50)
                logger.info(f"Spreadsheet ID: {spreadsheet_id}")
                logger.info(f"Update Range: {update_range}")
                logger.info(f"Row Values: {new_row_values}")
                
                # Convert all values to strings and handle None values
                final_values = []
                for value in new_row_values:
                    if value is None:
                        final_values.append('')
                    elif isinstance(value, (int, float)):
                        final_values.append(str(value))
                    else:
                        final_values.append(str(value))
                
                logger.info(f"Processed Values: {final_values}")
                
                # Construct the update request
                update_body = {'values': [final_values]}
                logger.info(f"Request Body: {update_body}")
                
                # Execute the update request
                logger.info("Executing update request...")
                update_response = sheets_client.sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption='USER_ENTERED',
                    body=update_body
                ).execute()
                
                # Log the response details
                logger.info("="*50)
                logger.info("API RESPONSE DETAILS")
                logger.info("="*50)
                logger.info(f"Response: {update_response}")
                
                if update_response.get('updatedRange'):
                    logger.info(f"✅ Successfully appended entry at row {next_row}")
                    logger.info(f"Updated Range: {update_response.get('updatedRange')}")
                    logger.info(f"Updated Cells: {update_response.get('updatedCells')}")
                    return True
                else:
                    logger.error("❌ Update failed - no updatedRange in response")
                    logger.error(f"Unexpected response format: {update_response}")
                    return False
                    
            except Exception as e:
                logger.error("="*50)
                logger.error("API ERROR DETAILS")
                logger.error("="*50)
                logger.error(f"Error Type: {type(e).__name__}")
                logger.error(f"Error Message: {str(e)}")
                logger.error("Full traceback:")
                import traceback
                logger.error(traceback.format_exc())
                logger.error("="*50)
                return False

        except Exception as e:
            logger.error("="*50)
            logger.error("FORM SUBMISSION ERROR")
            logger.error("="*50)
            logger.error(f"Error Type: {type(e).__name__}")
            logger.error(f"Error Message: {str(e)}")
            logger.error("Full traceback:")
            import traceback
            logger.error(traceback.format_exc())
            logger.error("="*50)
            return False
