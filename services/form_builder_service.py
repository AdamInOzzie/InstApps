"""Service for handling form building and submission operations."""
import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from datetime import datetime
import streamlit as st

logger = logging.getLogger(__name__)

class FormBuilderService:
    @staticmethod
    def is_formula(value: str) -> bool:
        """Check if a value is a formula."""
        return isinstance(value, str) and value.startswith('=')

    def get_form_fields(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract form fields from dataframe structure."""
        try:
            if df is None or df.empty:
                logger.error("No data provided to generate form fields")
                return []

            logger.info(f"Processing {len(df.columns)} columns from header row")
            form_fields = []
            
            # Process each column in the header row
            for col in df.columns:
                try:
                    logger.info(f"Processing header field: {col}")
                    
                    # Skip if column name is empty
                    if not col or pd.isna(col):
                        continue
                        
                    # Check the second row (index 1) for this column
                    if len(df) > 1:
                        second_row_value = df.iloc[1][col]
                        logger.info(f"Checking row 2 value for column {col}: {second_row_value}")
                        
                        # Skip if it's a formula field
                        is_formula = self.is_formula(str(second_row_value))
                        logger.info(f"Column {col} formula check result: {is_formula}")
                        
                        if is_formula:
                            logger.info(f"Skipping formula field {col}: {second_row_value}")
                            continue
                    
                    # Add field to form fields list
                    field = {
                        'name': col,
                        'type': 'text',  # Default to text input
                        'required': True if col in ['Name', 'Date'] else False
                    }
                    
                    logger.info(f"Added field '{col}' of type '{field['type']}'")
                    form_fields.append(field)
                    
                except Exception as e:
                    logger.error(f"Error processing column {col}: {str(e)}")
                    continue
            
            logger.info(f"Generated {len(form_fields)} form fields from header row")
            return form_fields
            
        except Exception as e:
            logger.error(f"Error generating form fields: {str(e)}")
            return []

    def render_form(self, form_fields: List[Dict[str, Any]], sheet_name: str) -> Dict[str, Any]:
        """Render form fields using Streamlit components."""
        try:
            form_data = {}
            
            # Display form header
            st.markdown(f"""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin-bottom: 1rem;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📝 Add New Entry</h3>
                </div>
            """, unsafe_allow_html=True)
            
            # Render form fields with consistent spacing
            for field in form_fields:
                try:
                    field_name = field['name']
                    field_type = field.get('type', 'text')
                    required = field.get('required', False)
                    
                    # Add label with required indicator if needed
                    label = f"{field_name}{'*' if required else ''}"
                    
                    # Render appropriate input field based on type
                    if field_type == 'text':
                        value = st.text_input(
                            label,
                            key=f"{sheet_name}_{field_name}",
                            help=f"Enter {field_name.lower()}"
                        )
                        if value:
                            form_data[field_name] = value
                            
                except Exception as e:
                    logger.error(f"Error rendering field {field_name}: {str(e)}")
                    continue
            
            return form_data
            
        except Exception as e:
            logger.error(f"Error rendering form: {str(e)}")
            return {}

    def validate_date_format(self, date_str: str) -> bool:
        """Validate date string format (DD/MM/YY)."""
        try:
            datetime.strptime(date_str, '%d/%m/%y')
            return True
        except ValueError:
            return False

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data to the spreadsheet."""
        try:
            logger.info("="*50)
            logger.info("FORM SUBMISSION DETAILS")
            logger.info("="*50)
            
            # Validate form data
            if not form_data:
                logger.error("Form data is empty")
                return False
            
            # Validate required fields
            if 'Name' not in form_data or 'Date' not in form_data:
                logger.error(f"Missing required fields. Found: {list(form_data.keys())}")
                return False
                
            # Validate date format
            if not self.validate_date_format(form_data['Date']):
                logger.error(f"Invalid date format: {form_data['Date']}")
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