"""Service for building and handling dynamic forms from Google Sheets."""
import logging
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd
import streamlit as st
from services.copy_service import CopyService

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

    def get_form_fields(self, sheet_data: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Extract form fields from sheet headers and check row 2 for formulas.
        
        Args:
            sheet_data: DataFrame containing the sheet data
            
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
                    return form_fields, {}
                logger.warning("Sheet is completely empty")
                return [], {}

            logger.info(f"Processing {len(sheet_data.columns)} columns from header row")
            form_fields = []
            formula_fields = {}
            
            # Process each column header as a field
            for col in sheet_data.columns:
                try:
                    logger.info(f"Processing header field: {col}")
                    
                    # Check row 2 for formulas if available
                    if len(sheet_data) > 1:
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
                                logger.info(f"Found formula field {col}: {str_value}")
                                formula_fields[col] = str_value
                                continue  # Skip adding this field to form fields
                    
                    # For non-formula fields, create form field
                    field_info = {
                        'name': col,
                        'type': 'text',
                        'required': True
                    }
                    
                    # Determine type from data
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
    def get_column_letter(column_index: int) -> str:
        """Convert column number to letter (1=A, 2=B, etc)."""
        result = ""
        while column_index > 0:
            column_index -= 1
            result = chr(65 + (column_index % 26)) + result
            column_index //= 26
        return result

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
                column_letter = self.get_column_letter(idx)
                field_label = f"{field_name}\n<span style='color: #666; font-size: 0.8em;'>Column {column_letter}</span>"
                
                if field_type == 'number':
                    step_size = 0.01 if float(field.get('min_value', 0)) < 10 else 1.0
                    form_data[field_name] = st.number_input(
                        field_label,
                        min_value=field.get('min_value', None),
                        max_value=field.get('max_value', None),
                        step=step_size,
                        value=0.0,
                        help=f"Updates column {column_letter}"
                    )
                elif field_type == 'date':
                    form_data[field_name] = st.date_input(
                        field_label,
                        help=f"Updates column {column_letter}"
                    )
                elif field_type == 'checkbox':
                    form_data[field_name] = st.checkbox(
                        field_label,
                        help=f"Updates column {column_letter}"
                    )
                elif field_type == 'percentage':
                    value = st.number_input(
                        f"{field_label} (%)",
                        step=0.1,
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        help=f"Updates column {column_letter}"
                    )
                    form_data[field_name] = f"{value}%"
                elif field_type == 'currency':
                    value = st.number_input(
                        field_label,
                        step=0.01,
                        min_value=0.0,
                        value=0.0,
                        help=f"Updates column {column_letter}"
                    )
                    form_data[field_name] = f"${value:.2f}"
                else:
                    form_data[field_name] = st.text_input(
                        field_label,
                        value="",
                        help=f"Updates column {column_letter}"
                    )
                    
            except Exception as e:
                logger.error(f"Error rendering field {field_name}: {str(e)}")
                st.error(f"Error rendering field {field_name}")
                
        return form_data

    def append_form_data(self, spreadsheet_id: str, sheet_name: str, form_data: Dict[str, Any], sheets_client) -> bool:
        """Append form data as a new row in the sheet by copying row 2 as template."""
        try:
            logger.info("Starting form data append process")
            
            # Get sheet data to determine next row
            range_name = f"{sheet_name}!A1:Z1000"
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            if df.empty:
                logger.error("Sheet is empty")
                return False
            
            next_row = len(df) + 2  # Add to next empty row
            logger.info(f"Copying template to row {next_row}")
            
            # Use copy service to copy row 2 to the next row
            copy_service = CopyService(sheets_client)
            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                source_range="A2:D2",  # Use exact same range as working copy function
                target_row=int(next_row)  # Ensure target_row is int
            )
            
            if not success:
                logger.error("Failed to copy template row")
                return False
                
            logger.info("Successfully copied template row")
            return True
                
        except Exception as e:
            logger.error(f"Error in append_form_data: {str(e)}")
            logger.exception("Full traceback:")
            return False
