"""Service for handling dynamic form operations."""
import logging
from typing import Tuple, Any, Optional
import pandas as pd
from utils import GoogleSheetsClient

logger = logging.getLogger(__name__)

class FormService:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client

    def get_input_field_data(self, spreadsheet_id: str) -> Tuple[str, Any]:
        """Get input field data from INPUTS sheet."""
        try:
            inputs_range = "INPUTS!A2:B2"
            cell_data = self.sheets_client.read_spreadsheet(spreadsheet_id, inputs_range)
            
            if cell_data.empty:
                logger.warning("No data found in INPUTS sheet cells A2:B2")
                return None, None
                
            field_name = cell_data.iloc[0, 0]  # A2 value
            current_value = cell_data.iloc[0, 1]  # B2 value
            return field_name, current_value
            
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
                return numeric_value, str(numeric_value)
            else:
                return None, str(value)
        except ValueError as e:
            logger.error(f"Error processing input value: {str(e)}")
            raise
