"""Service for handling spreadsheet operations."""
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
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
        """Read data from a specific sheet."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            logger.debug(f"Reading data from range: {range_name}")
            df = self.sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            logger.info(f"Successfully loaded data: {df.shape[0]} rows, {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"Failed to read sheet data: {str(e)}")
            raise

    def upload_csv_data(self, spreadsheet_id: str, sheet_name: str, df: pd.DataFrame) -> bool:
        """Upload CSV data to a sheet."""
        try:
            range_name = f"{sheet_name}!A1:Z1000"
            logger.debug(f"Writing data to sheet: {range_name}")
            values = [df.columns.tolist()] + df.values.tolist()
            return self.sheets_client.write_to_spreadsheet(spreadsheet_id, range_name, values)
        except Exception as e:
            logger.error(f"Failed to upload data: {str(e)}")
            raise

    def update_input_cell(self, spreadsheet_id: str, value: str) -> bool:
        """Update B3 cell in INPUTS sheet."""
        try:
            update_range = "INPUTS!B3"
            return self.sheets_client.write_to_spreadsheet(
                spreadsheet_id,
                update_range,
                [[value]]
            )
        except Exception as e:
            logger.error(f"Failed to update cell B3: {str(e)}")
            raise
