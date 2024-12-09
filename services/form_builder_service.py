"""Service for building and handling dynamic forms from Google Sheets."""
import logging
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

class FormBuilderService:
    @staticmethod
    def is_formula(value: Any) -> bool:
        """Check if a cell value is a formula.
        
        Args:
            value: The cell value to check
            
        Returns:
            bool: True if the value is a formula, False otherwise
        """
        if pd.isna(value):
            return False
        str_value = str(value).strip()
        # Check if the value starts with = and contains any mathematical operators or functions
        return str_value.startswith('=') and any(op in str_value for op in ['+', '-', '*', '/', '(', ')', 'SUM', 'AVERAGE', 'COUNT'])

    @staticmethod
    def get_field_type(value: Any) -> str:
        """Determine the appropriate field type based on the sample value."""
        if pd.isna(value):
            return 'text'  # Default to text for empty cells
            
        if isinstance(value, (int, float)):
            return 'number'
        elif isinstance(value, bool):
            return 'checkbox'
        elif isinstance(value, pd.Timestamp):
            return 'date'
        else:
            # Check if it's a percentage or currency
            str_value = str(value).strip()
            if str_value.endswith('%'):
                return 'percentage'
            elif str_value.startswith('$'):
                return 'currency'
            return 'text'

    def get_form_fields(self, sheet_data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract form fields from sheet headers, excluding formula fields.
        
        Args:
            sheet_data: DataFrame containing the sheet data
            
        Returns:
            List of dictionaries containing field information for non-formula fields
        """
        if sheet_data.empty or len(sheet_data.columns) == 0:
            logger.warning("Empty sheet data provided")
            return []

        form_fields = []
        # Get the first row to check for formulas
        first_row = sheet_data.iloc[0] if len(sheet_data) > 0 else pd.Series()
        
        for col in sheet_data.columns:
            try:
                # Get the first row value for this column
                first_row_value = first_row[col] if not first_row.empty else None
                
                # Skip if it's a formula
                if self.is_formula(first_row_value):
                    logger.info(f"Skipping formula field: {col} with value {first_row_value}")
                    continue
                
                # Determine field type and add to form fields
                field_type = self.get_field_type(first_row_value)
                field_info = {
                    'name': col,
                    'type': field_type,
                    'sample_value': first_row_value,
                    'required': True  # Make all fields required by default
                }
                
                # Add validation based on field type
                if field_type == 'number':
                    # Find min/max values in the column for validation
                    numeric_values = pd.to_numeric(sheet_data[col], errors='coerce')
                    field_info['min_value'] = float(numeric_values.min()) if not numeric_values.empty else None
                    field_info['max_value'] = float(numeric_values.max()) if not numeric_values.empty else None
                
                form_fields.append(field_info)
                logger.debug(f"Added field {col} of type {field_type}")
                
            except Exception as e:
                logger.error(f"Error processing field {col}: {str(e)}")
                continue
            
        return form_fields

    def render_form(self, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Render a dynamic form based on field definitions."""
        form_data = {}
        
        # Add form header
        st.markdown("""
            <div style="
                background-color: #f0f8ff;
                padding: 0.5rem 0.8rem;
                border-radius: 8px;
                border-left: 5px solid #1E88E5;
                margin-bottom: 0.6rem;
            ">
                <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📝 New Entry Form</h3>
            </div>
        """, unsafe_allow_html=True)

        # Create form fields
        for field in fields:
            try:
                field_name = field['name']
                field_type = field['type']
                sample_value = field.get('sample_value')
                
                if field_type == 'number':
                    # Determine step size based on sample value
                    step_size = 0.01 if sample_value and abs(float(sample_value or 0)) < 10 else 1.0
                    form_data[field_name] = st.number_input(
                        field_name,
                        step=step_size,
                        value=float(sample_value) if sample_value and not pd.isna(sample_value) else 0.0
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
                        value=float(str(sample_value).rstrip('%')) if sample_value else 0.0
                    )
                    form_data[field_name] = f"{value}%"
                elif field_type == 'currency':
                    value = st.number_input(
                        field_name,
                        step=0.01,
                        min_value=0.0,
                        value=float(str(sample_value).lstrip('$').replace(',', '')) if sample_value else 0.0
                    )
                    form_data[field_name] = f"${value:.2f}"
                else:
                    form_data[field_name] = st.text_input(
                        field_name,
                        value=str(sample_value) if sample_value and not pd.isna(sample_value) else ""
                    )
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
        return form_data

    def append_form_data(self, 
                        spreadsheet_id: str,
                        sheet_name: str,
                        form_data: Dict[str, Any],
                        sheets_client) -> bool:
        """Append form data as a new row in the sheet."""
        try:
            # Get existing data to determine the next row
            range_name = f"{sheet_name}!A1:Z1000"
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            next_row = len(df) + 2  # Add 2 to account for header row and 1-based indexing
            
            # Prepare the values to append
            headers = list(form_data.keys())
            values = [[form_data[header] for header in headers]]
            
            # Append the new row
            append_range = f"{sheet_name}!A{next_row}"
            success = sheets_client.write_to_spreadsheet(
                spreadsheet_id,
                append_range,
                values
            )
            
            if success:
                logger.info(f"Successfully appended new row to {sheet_name}")
                return True
            else:
                logger.error("Failed to append row")
                return False
                
        except Exception as e:
            logger.error(f"Error appending form data: {str(e)}")
            raise

    def check_append_permission(self, sheets_client, spreadsheet_id: str, username: str, sheet_name: str) -> bool:
        """Check if user has permission to append to a specific sheet.
        
        Args:
            sheets_client: The Google Sheets client instance
            spreadsheet_id: The ID of the spreadsheet
            username: The username to check permissions for
            sheet_name: The name of the sheet to check append permissions for
            
        Returns:
            bool: True if user has append permission, False otherwise
        """
        try:
            # Read USERS sheet
            users_df = sheets_client.read_spreadsheet(spreadsheet_id, 'USERS!A1:Z1000')
            if users_df is None or users_df.empty:
                logger.warning("Empty USERS sheet")
                return False
            
            # Find user's row (case-insensitive match)
            user_row = users_df[users_df['User Name'].str.lower() == username.lower()]
            if user_row.empty:
                logger.warning(f"User {username} not found in USERS sheet")
                return False
                
            # Check APPENDALL column for sheet permissions
            if 'APPENDALL' not in users_df.columns:
                logger.warning("APPENDALL column not found in USERS sheet")
                return False
                
            # Get user's APPENDALL value
            append_permissions = user_row['APPENDALL'].iloc[0]
            if pd.isna(append_permissions):
                return False
                
            # Split permissions and check if sheet_name is included
            allowed_sheets = str(append_permissions).split(',')
            return sheet_name.strip() in [s.strip() for s in allowed_sheets]
            
        except Exception as e:
            logger.error(f"Error checking append permission: {str(e)}")
            return False

