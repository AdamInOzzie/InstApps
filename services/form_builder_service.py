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
        # Check for more Excel/Google Sheets formula patterns
        return (str_value.startswith('=') and 
                any(op in str_value.upper() for op in [
                    '+', '-', '*', '/', '(', ')', 
                    'SUM', 'AVERAGE', 'COUNT', 'IF', 
                    'VLOOKUP', 'INDEX', 'MATCH', 'CONCATENATE'
                ]))

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
                        if row2_value is not None and isinstance(row2_value, str) and self.is_formula(row2_value):
                            logger.info(f"Found formula in column {col}: {row2_value}")
                            field_info['is_formula'] = True
                            field_info['formula_value'] = row2_value
                            field_info['type'] = 'formula_display'
                            continue
                    
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
                    if field.get('type') == 'formula_display':
                        # Display formula fields as read-only
                        st.text_input(
                            f"{field_name} (Formula)",
                            value=field.get('formula_value', ''),
                            disabled=True
                        )
                        # Store formula information for later
                        st.session_state.formula_fields[field_name] = field.get('formula_value')
                        # Don't add to form_data as we don't want to update formula fields
                    else:
                        form_data[field_name] = st.text_input(field_name, value="")
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
        return form_data

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data as a new row in the sheet, copying the last row for formula fields."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            if df.empty:
                logger.error("Sheet is empty")
                return False
                
            next_row = len(df) + 2
            last_data_row = df.iloc[-1].to_dict()  # Get the last row with data
            
            # Create new row by copying the last row
            new_row = []
            for col in df.columns:
                if col in st.session_state.get('formula_fields', {}):
                    # For formula fields, copy from last row
                    new_row.append(last_data_row[col])
                elif col in form_data:
                    # For non-formula fields, use form input
                    new_row.append(form_data[col])
                else:
                    # For any other fields, copy from last row
                    new_row.append(last_data_row[col])
            
            append_range = f"{sheet_name}!A{next_row}"
            success = sheets_client.write_to_spreadsheet(
                spreadsheet_id,
                append_range,
                [new_row]  # Wrap in list as write_to_spreadsheet expects list of rows
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
