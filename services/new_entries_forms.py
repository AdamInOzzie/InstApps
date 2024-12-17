"""Service for handling new entries form operations."""
import logging
import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from services.form_builder_service import FormBuilderService
from services.spreadsheet_service import SpreadsheetService
from services.copy_service import CopyService
from services.ui_service import UIService

# Configure logging
logger = logging.getLogger(__name__)

class FormField:
    """Represents a form field with its metadata."""
    def __init__(self, name: str, column_letter: str, column_index: int, current_value: Any, is_formula: bool = False):
        self.name = name
        self.column_letter = column_letter  # A1 notation (e.g., 'A', 'B', 'C')
        self.column_index = column_index  # 0-based index
        self.current_value = current_value
        self.is_formula = is_formula

    def __repr__(self):
        return f"FormField(name='{self.name}', column='{self.column_letter}', index={self.column_index}, is_formula={self.is_formula})"

    @staticmethod
    def get_column_letter(index: int) -> str:
        """Convert 0-based column index to A1 notation letter."""
        return chr(65 + index)  # A = 65 in ASCII

class NewEntriesFormsService:
    """Service for handling form operations and sheet selection."""
    
    def __init__(self, spreadsheet_service: SpreadsheetService, form_builder_service: FormBuilderService):
        """Initialize the service with required dependencies."""
        self.spreadsheet_service = spreadsheet_service
        self.form_builder_service = form_builder_service
        self.ui_service = UIService()
        
    def detect_formula_fields(self, spreadsheet_id: str, sheet_name: str, row_number: int = 2) -> Dict[str, bool]:
        """Detect which fields contain formulas in the specified row."""
        logger.info(f"Detecting formula fields in sheet {sheet_name}, row {row_number}")
        formula_fields = {}
        
        try:
            # Get sheet metadata to determine column names
            metadata = self.spreadsheet_service.get_sheet_metadata(spreadsheet_id)
            first_sheet_id = metadata['sheets'][0]['properties']['sheetId']
            
            # Get detailed cell data including formulas
            cell_data = self.spreadsheet_service.sheets_client.get(
                spreadsheetId=spreadsheet_id,
                ranges=[f"{sheet_name}!A{row_number}:Z{row_number}"],
                fields="sheets/data/rowData/values(userEnteredValue,effectiveValue)"
            ).execute()
            
            # Get column headers
            headers_data = self.spreadsheet_service.read_sheet_data(spreadsheet_id, f"{sheet_name}!A1:Z1")
            if headers_data is None or headers_data.empty:
                return {}
                
            headers = headers_data.columns.tolist()
            
            # Process each cell in the row
            try:
                row_data = cell_data['sheets'][0]['data'][0]['rowData'][0]['values']
                for idx, cell in enumerate(row_data):
                    if idx < len(headers):
                        field_name = headers[idx]
                        has_formula = 'userEnteredValue' in cell and 'formulaValue' in cell['userEnteredValue']
                        formula_fields[field_name] = has_formula
                        if has_formula:
                            logger.info(f"Found formula in column {field_name}")
                    
            except (KeyError, IndexError) as e:
                logger.error(f"Error processing row data: {str(e)}")
                
            return formula_fields
            
        except Exception as e:
            logger.error(f"Error detecting formula fields: {str(e)}")
            return {}
            
    def get_form_fields(self, spreadsheet_id: str, sheet_name: str) -> List[FormField]:
        """Get form fields with their column positions and formula status."""
        logger.info(f"Getting form fields for sheet {sheet_name}")
        try:
            # Read the first two rows to get headers and sample data
            range_name = f"{sheet_name}!A1:Z2"
            df = self.spreadsheet_service.read_sheet_data(spreadsheet_id, range_name)
            
            if df is None or df.empty:
                logger.error("No data found in sheet")
                return []
                
            # Detect formula fields
            formula_fields = self.detect_formula_fields(spreadsheet_id, sheet_name)
            
            # Create form fields with column mapping
            form_fields = []
            for idx, column in enumerate(df.columns):
                # Skip empty column names
                if pd.isna(column) or str(column).strip() == '':
                    continue
                    
                # Get sample value from second row if available
                current_value = df.iloc[0, idx] if len(df) > 0 else None
                
                # Convert index to column letter (A1 notation)
                column_letter = FormField.get_column_letter(idx)
                
                # Create form field with column mapping
                field = FormField(
                    name=column,
                    column_letter=column_letter,
                    column_index=idx,  # 0-based index
                    current_value=current_value,
                    is_formula=formula_fields.get(column, False)
                )
                
                # Skip formula fields - they shouldn't be editable
                if field.is_formula:
                    logger.info(f"Skipping formula field: {field}")
                    continue
                    
                form_fields.append(field)
                logger.info(f"Created form field: {field}")
                
            return form_fields
            
        except Exception as e:
            logger.error(f"Error getting form fields: {str(e)}")
            return []
            
    def render_form(self, form_fields: List[FormField]) -> Dict[str, Dict[str, Any]]:
        """Render form fields and return their values with column positions."""
        logger.info("Rendering form fields")
        field_values = {}
        
        try:
            with st.form(key="entry_form"):
                for field in form_fields:
                    if not field.is_formula:  # Only render non-formula fields
                        logger.info(f"Rendering field: {field.name} (column {field.column_letter}, index {field.column_index})")
                        value = st.text_input(
                            field.name,
                            value="" if pd.isna(field.current_value) else str(field.current_value),
                            key=f"field_{field.name}"
                        )
                        # Store field metadata including column information
                        field_values[field.name] = {
                            'value': value,
                            'column_index': field.column_index,  
                            'column_letter': field.column_letter,
                            'is_formula': field.is_formula
                        }
                
                submitted = st.form_submit_button("Submit Entry")
                if submitted:
                    return field_values
                return None
            
        except Exception as e:
            logger.error(f"Error rendering form: {str(e)}")
            return {}
            
    def handle_form_submission(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        form_data: Dict[str, Dict[str, Any]],  # Changed to store field metadata
        copy_service: CopyService
    ) -> bool:
        """Handle form submission with correct column mapping."""
        logger.info("=" * 80)
        logger.info("FORM SUBMISSION HANDLER")
        logger.info("=" * 80)
        logger.info(f"Processing submission for sheet: {sheet_name}")
        logger.info(f"Form data received: {form_data}")
        
        try:
            # Get next available row
            entry_range = f"{sheet_name}!A:A"
            entry_df = self.spreadsheet_service.read_sheet_data(spreadsheet_id, entry_range)
            next_row = int(2 if entry_df.empty else entry_df[entry_df.columns[0]].notna().sum() + 2)
            
            # Copy template row
            source_range = f"{sheet_name}!A2:Z2"
            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                source_range=source_range,
                target_row=next_row
            )
            
            if not success:
                logger.error("Failed to copy entry template")
                return False
                
            # Prepare cell updates using correct column positions
            cell_updates = []
            for field_name, field_data in form_data.items():
                value = field_data['value']
                column_index = field_data['column_index']
                column_letter = field_data['column_letter']
                
                logger.info(f"Updating field '{field_name}' at {column_letter}{next_row} with value '{value}'")
                # Add row, column, value for batch update (using 1-based column index)
                cell_updates.extend([next_row, column_index + 1, str(value)])
                
            if cell_updates:
                # Execute batch update
                success = self.spreadsheet_service.batch_update_cells(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    cell_updates=cell_updates
                )
                
                if success:
                    logger.info(f"Successfully updated cells in row {next_row}")
                    st.success(f"✅ Successfully added new entry!")
                    return True
                else:
                    logger.error("Failed to update cells")
                    st.error("Failed to update cells")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error in form submission: {str(e)}")
            st.error(f"Error submitting form: {str(e)}")
            return False
            
    def handle_new_entry(self, spreadsheet_id: str, sheet_name: str, copy_service: CopyService) -> bool:
        """Handle the complete process of creating a new entry."""
        try:
            # Get form fields with correct column mapping
            form_fields = self.get_form_fields(spreadsheet_id, sheet_name)
            
            if not form_fields:
                st.warning(f"No form fields found in sheet '{sheet_name}'")
                return False
                
            # Render form and get values with column positions
            form_data = self.render_form(form_fields)
            
            # Handle form submission
            if form_data and st.button("Submit Entry", type="primary"): # Added check for form_data
                return self.handle_form_submission(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    form_data=form_data,
                    copy_service=copy_service
                )
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling new entry: {str(e)}")
            st.error(f"Error: {str(e)}")
            return False

    def handle_sheet_selection(self, spreadsheets: List[Dict[str, Any]], current_sheet_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Handle sheet selection and maintain selection state."""
        try:
            if not spreadsheets:
                st.warning("📝 No spreadsheets available")
                st.info("""
                    Possible reasons:
                    - Service account has no access to any spreadsheets
                    - No spreadsheets exist in the account
                    - Connection issues with Google API
                """)
                return None
                
            selected_sheet = st.selectbox(
                "Pick an Instapp",
                options=spreadsheets,
                format_func=lambda x: x['name'],
                key='sheet_selector'
            )
            
            # Clear login state if switching sheets
            if current_sheet_id and selected_sheet['id'] != current_sheet_id:
                st.session_state.is_logged_in = False
                st.session_state.username = None
                st.session_state.current_sheet_id = selected_sheet['id']
                
            return selected_sheet
            
        except Exception as e:
            logger.error(f"Error in sheet selection: {str(e)}")
            st.error("⚠️ Error loading spreadsheets")
            return None
            
    def display_sheet_data(self, df: pd.DataFrame, sheet_name: str):
        """Display sheet data with appropriate formatting."""
        try:
            UIService.display_data_quality_report(df)
            UIService.display_sheet_data(df, sheet_type='general')
        except Exception as e:
            logger.error(f"Error displaying sheet data: {str(e)}")
            st.error("Error displaying sheet data")