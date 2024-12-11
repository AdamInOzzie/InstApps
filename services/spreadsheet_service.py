"""Service for handling spreadsheet operations."""
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from utils import GoogleSheetsClient

logger = logging.getLogger(__name__)

class SpreadsheetService:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client

    def list_spreadsheets(self) -> List[Dict[str, str]]:
        """Get list of available spreadsheets."""
        try:
            logger.debug("Fetching spreadsheets list")
            spreadsheets = self.sheets_client.list_spreadsheets()
            logger.info(f"Successfully loaded {len(spreadsheets)} spreadsheets")
            return spreadsheets
        except Exception as e:
            logger.error(f"Failed to list spreadsheets: {str(e)}")
            raise

    def get_sheet_metadata(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Get metadata for a specific spreadsheet."""
        try:
            logger.debug(f"Fetching metadata for spreadsheet: {spreadsheet_id}")
            metadata = self.sheets_client.get_spreadsheet_metadata(spreadsheet_id)
            sheets = metadata.get('sheets', [])
            logger.info(f"Found {len(sheets)} sheets in spreadsheet")
            return metadata
        except Exception as e:
            logger.error(f"Failed to load spreadsheet metadata: {str(e)}")
            raise

    def read_sheet_data(self, spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
        """Read data from a specific sheet while preserving original formatting."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            logger.debug(f"Reading data from range: {range_name}")
            # Use FORMATTED_VALUE to get calculated results instead of formulas
            df = self.sheets_client.read_spreadsheet(spreadsheet_id, range_name, value_render_option='FORMATTED_VALUE')
            
            # Process each column while preserving formatting
            for col in df.columns:
                if df[col].dtype == 'object':
                    # Create a mask for currency values
                    currency_mask = df[col].astype(str).str.contains('^\$', na=False)
                    # Create a mask for percentage values
                    percent_mask = df[col].astype(str).str.contains('%$', na=False)
                    
                    # Store the original formatted strings
                    formatted_values = df[col].copy()
                    
                    try:
                        # Convert currency values while preserving format
                        if currency_mask.any():
                            # Store original formatted strings
                            df[col + '_formatted'] = formatted_values
                            # Convert to numeric values for calculations
                            df.loc[currency_mask, col] = df.loc[currency_mask, col].apply(
                                lambda x: float(str(x).replace('$', '').replace(',', ''))
                                if pd.notnull(x) and isinstance(x, str) else x
                            )

                        # Convert percentage values while preserving format and value
                        elif percent_mask.any():
                            # Store original formatted strings
                            df[col + '_formatted'] = formatted_values
                            # Convert to numeric values as full percentages
                            df.loc[percent_mask, col] = df.loc[percent_mask, col].apply(
                                lambda x: float(str(x).rstrip('%'))
                                if pd.notnull(x) and isinstance(x, str) else x
                            )

                        # Handle percentage fields (including Allocation, Rate, etc.)
                        elif 'Allocation' in col or any(term in col for term in ['Rate', 'Yield']):
                            # For decimal values (e.g., 0.59), convert to percentage string
                            df[col + '_formatted'] = df[col].apply(
                                lambda x: f"{float(x)*100:.2f}%" if isinstance(x, (int, float)) and x <= 1
                                else (f"{float(str(x).rstrip('%')):.2f}%" if isinstance(x, str) and '%' in x
                                else str(x))
                            )
                            # Store numeric value as percentage
                            df[col] = df[col].apply(
                                lambda x: float(str(x).rstrip('%')) if isinstance(x, str) and '%' in str(x)
                                else float(x) * 100 if isinstance(x, (int, float)) and x <= 1
                                else float(x)
                            )

                        # Convert remaining numeric values
                        else:
                            remaining_mask = ~(currency_mask | percent_mask) & df[col].notna()
                            if remaining_mask.any():
                                temp_values = pd.to_numeric(df.loc[remaining_mask, col], errors='coerce')
                                valid_numeric_mask = temp_values.notna()
                                if valid_numeric_mask.any():
                                    df.loc[remaining_mask[remaining_mask].index[valid_numeric_mask], col] = temp_values[valid_numeric_mask]

                    except Exception as e:
                        logger.debug(f"Conversion failed for column {col}: {str(e)}")
                        continue
                
                # Ensure float columns maintain float type
                elif df[col].dtype in ['float64', 'float32']:
                    df[col] = df[col].astype('float64')
            
            # Log detailed information about the data types and sample values
            logger.info(f"Successfully loaded data: {df.shape[0]} rows, {df.shape[1]} columns")
            logger.info("Column types and sample values:")
            for col in df.columns:
                sample_values = df[col].head(3).tolist()
                logger.info(f"Column '{col}': type={df[col].dtype}, samples={sample_values}")
            logger.debug(f"Column types after conversion: {df.dtypes.to_dict()}")
            return df
        except Exception as e:
            logger.error(f"Failed to read sheet data: {str(e)}")
            raise

    def upload_csv_data(self, spreadsheet_id: str, sheet_name: str, df: pd.DataFrame) -> bool:
        """Upload CSV data to a sheet with proper type handling."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            logger.debug(f"Writing data to sheet: {range_name}")
            
            # Create a copy to avoid modifying the original dataframe
            df_formatted = df.copy()
            
            # Format numeric columns for consistent display
            for col in df_formatted.columns:
                if df_formatted[col].dtype in ['float64', 'float32']:
                    # Format percentages if the column contains percentage values
                    if df_formatted[col].astype(str).str.contains('%', na=False).any():
                        df_formatted[col] = df_formatted[col].map(lambda x: f"{x:.1%}" if pd.notnull(x) else '')
                    else:
                        # Use fixed precision for normal float values
                        df_formatted[col] = df_formatted[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else '')
            
            values = [df_formatted.columns.tolist()] + df_formatted.values.tolist()
            logger.debug(f"Uploading data with types: {df_formatted.dtypes.to_dict()}")
            return self.sheets_client.write_to_spreadsheet(spreadsheet_id, range_name, values)
        except Exception as e:
            logger.error(f"Failed to upload data: {str(e)}")
            raise

    def update_input_cell(self, spreadsheet_id: str, value: str, row: int) -> bool:
        """Update cell in B column of INPUTS sheet for specified row."""
        try:
            import streamlit as st
            
            # Construct the range in A1 notation for column B
            update_range = f"INPUTS!B{row}"
            
            # Format the value appropriately based on type
            if isinstance(value, (int, float)):
                if value <= 1 and value >= 0:  # Likely a percentage
                    formatted_value = f"{value:.4f}"  # Keep precision for small decimals
                else:
                    formatted_value = f"{value:.2f}"  # Normal number formatting
            else:
                formatted_value = str(value).strip()
            
            logger.info(f"Updating cell {update_range} with value: {formatted_value}")
            
            try:
                result = self.sheets_client.sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption='USER_ENTERED',
                    body={'values': [[formatted_value]]}
                ).execute()
                
                updated_cells = result.get('updatedCells', 0)
                if updated_cells > 0:
                    logger.info(f"Successfully updated cell {update_range}")
                    return True
                else:
                    logger.error(f"No cells were updated in range {update_range}")
                    return False
                    
            except Exception as update_error:
                logger.error(f"Error updating cell {update_range}: {str(update_error)}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating cell: {str(e)}")
            return False


    @staticmethod
    def UpdateEntryCells(spreadsheet_id: str, sheet_name: str, cell_updates: list) -> bool:
        """
        Update multiple cells in a sheet with provided values.
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet to update
            cell_updates: List of updates in format [row1, col1, value1, row2, col2, value2, ...]
                         where row/col are 1-based indices
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not cell_updates or len(cell_updates) % 3 != 0:
                logger.error("Invalid cell_updates format")
                return False
                
            # Group updates into batches of 3 (row, col, value)
            updates = []
            for i in range(0, len(cell_updates), 3):
                try:
                    row, col, value = cell_updates[i:i+3]
                    
                    # Validate row and column numbers
                    if not isinstance(row, int) or not isinstance(col, int):
                        logger.error(f"Invalid row ({row}) or column ({col}) number")
                        continue
                    if row < 1 or col < 1:
                        logger.error(f"Row ({row}) and column ({col}) must be positive")
                        continue
                        
                    # Convert column number to letter(s)
                    col_letter = ""
                    col_num = col - 1  # Convert to 0-based for calculation
                    while col_num >= 0:
                        col_letter = chr(65 + (col_num % 26)) + col_letter
                        col_num = col_num // 26 - 1
                        
                    cell_range = f"{sheet_name}!{col_letter}{row}"
                    updates.append({
                        'range': cell_range,
                        'values': [[value]]
                    })
                    logger.debug(f"Adding update for cell {cell_range} with value: {value}")
                    
                except Exception as e:
                    logger.error(f"Error processing update at index {i}: {str(e)}")
                    continue
            
            if not updates:
                logger.error("No valid updates to process")
                return False
                
            # Create batch update request
            body = {
                'valueInputOption': 'USER_ENTERED',
                'data': updates
            }
            
            # Execute the batch update using the client singleton
            client = GoogleSheetsClient()
            # Log API method being used
            logger.info("Calling Google Sheets API Method: spreadsheets.values.batchUpdate")
            logger.info("API Request Parameters:")
            logger.info(f"  - Method: values.batchUpdate")
            logger.info(f"  - Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"  - Body Structure:")
            logger.info(f"    - Value Input Option: {body['valueInputOption']}")
            logger.info(f"    - Updates Count: {len(body['data'])}")
            logger.info(f"    - Full Body: {body}")
            
            result = client.sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()
            
            # Log the raw API response
            logger.info("Raw API Response:")
            logger.info(str(result))
            
            updated_cells = len(updates)
            logger.info(f"Successfully updated {updated_cells} cell{'s' if updated_cells != 1 else ''}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating cells: {str(e)}")
            return False
