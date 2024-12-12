"""Service for handling dynamic form operations."""
import logging
from typing import Tuple, Any, Optional, List
import pandas as pd
from utils import GoogleSheetsClient

logger = logging.getLogger(__name__)

class FormService:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client

    def get_input_field_data(self, spreadsheet_id: str) -> List[Tuple[str, Any]]:
        """Get input field data from INPUTS sheet."""
        try:
            inputs_range = "INPUTS!A1:B100"  # Read all rows from 1 onwards
            cell_data = self.sheets_client.read_spreadsheet(spreadsheet_id, inputs_range)
            
            if cell_data.empty:
                logger.warning("No data found in INPUTS sheet")
                return []
            
            fields = []
            # Add debug logging
            logger.debug(f"Raw cell data:\n{cell_data}")
            
            # Process each row in the data
            for sheet_row_num in range(1, len(cell_data) + 1):
                try:
                    # Get row data safely
                    row = cell_data.iloc[sheet_row_num - 1] if sheet_row_num <= len(cell_data) else None
                    if row is None:
                        continue

                    field_name = row.iloc[0]
                    current_value = row.iloc[1]
                    
                    # Only skip if both values are empty
                    if pd.isna(field_name) and pd.isna(current_value):
                        logger.warning(f"Empty row found at row {sheet_row_num}")
                        continue
                        
                    logger.info(f"Successfully read field_name: {field_name}, current_value: {current_value}")
                    fields.append((field_name, current_value))
                except Exception as e:
                    logger.error(f"Error accessing values for row {sheet_row_num}: {str(e)}")
                    continue
            
            logger.info(f"Total fields processed: {len(fields)}")
            return fields
            
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
                # Check if this field should be displayed as percentage
                if numeric_value <= 1 and "rate" in str(value).lower():
                    display_value = f"{numeric_value * 100:.2f}%"  # Keep percentages at 2 decimal places
                elif numeric_value < 10:
                    display_value = f"{numeric_value:.3f}"  # 3 decimal places for values under 10
                else:
                    display_value = f"{numeric_value:.2f}"  # 2 decimal places for larger values
                return numeric_value, display_value
            else:
                return None, str(value)
        except ValueError as e:
            logger.error(f"Error processing input value: {str(e)}")
            raise
