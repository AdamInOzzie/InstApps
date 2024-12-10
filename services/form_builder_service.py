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
        return str_value.startswith('=') and any(op in str_value for op in ['+', '-', '*', '/', '(', ')', 'SUM', 'AVERAGE', 'COUNT'])

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
        """Extract form fields from sheet headers (Row A).
        
        Args:
            sheet_data: DataFrame containing the sheet data
            
        Returns:
            List of form field definitions based on header row
        """
        if len(sheet_data.columns) == 0:
            logger.warning("No columns found in sheet")
            return []

        logger.info(f"Processing {len(sheet_data.columns)} columns from header row")
        form_fields = []
        
        # Process each column header as a field
        for col in sheet_data.columns:
            try:
                logger.debug(f"Processing header field: {col}")
                
                # Get a sample value from data rows if any exist
                sample_values = sheet_data[col].dropna()
                sample_value = sample_values.iloc[0] if len(sample_values) > 0 else None
                
                # Default to text type, then try to infer from sample data
                field_type = 'text'
                if sample_value is not None:
                    if isinstance(sample_value, str) and self.is_formula(sample_value):
                        logger.info(f"Skipping formula field: {col}")
                        continue
                    field_type = self.get_field_type(sample_value)
                
                field_info = {
                    'name': col,
                    'type': field_type,
                    'required': True
                }
                
                # Add numeric constraints if we have sample data
                if field_type == 'number' and len(sample_values) > 0:
                    try:
                        numeric_values = pd.to_numeric(sample_values, errors='coerce').dropna()
                        if not numeric_values.empty:
                            field_info['min_value'] = float(numeric_values.min())
                            field_info['max_value'] = float(numeric_values.max())
                    except Exception as e:
                        logger.warning(f"Could not determine numeric constraints for {col}: {e}")
                
                form_fields.append(field_info)
                logger.info(f"Added field '{col}' of type '{field_type}'")
                
            except Exception as e:
                logger.error(f"Error processing field {col}: {str(e)}")
                continue
            
        logger.info(f"Generated {len(form_fields)} form fields from header row")
        return form_fields

    def render_form(self, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Render a dynamic form based on field definitions."""
        form_data = {}
        
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
        
        for field in fields:
            try:
                field_name = field['name']
                field_type = field['type']
                sample_value = field.get('sample_value')
                
                if field_type == 'number':
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

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data as a new row in the sheet."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            next_row = len(df) + 2
            
            headers = list(form_data.keys())
            values = [[form_data[header] for header in headers]]
            
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

    # Authentication methods will be added later