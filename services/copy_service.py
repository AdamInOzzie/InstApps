"""Service for handling copy operations in Google Sheets."""
import logging
from typing import Optional, Dict, Any
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class CopyService:
    def __init__(self, sheets_client):
        self.sheets_client = sheets_client
        
    def _get_sheet_id(self, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
        """Get the sheet ID for a given sheet name."""
        try:
            metadata = self.sheets_client.get_spreadsheet_metadata(spreadsheet_id)
            for sheet in metadata.get('sheets', []):
                properties = sheet.get('properties', {})
                if properties.get('title') == sheet_name:
                    return properties.get('sheetId')
            logger.error(f"Sheet '{sheet_name}' not found")
            return None
        except Exception as e:
            logger.error(f"Error getting sheet ID: {str(e)}")
            return None

    def copy_entry(self, spreadsheet_id: str, sheet_name: str, source_range: str, target_row: int) -> bool:
        """
        Copy a range to a target row using Google Sheets API.
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet
            source_range: Range to copy (e.g., "A2:D2")
            target_row: Target row number (e.g., 6)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Copying {source_range} to row {target_row} in sheet {sheet_name}")
            
            # Get sheet ID
            sheet_id = self._get_sheet_id(spreadsheet_id, sheet_name)
            if sheet_id is None:
                return False
                
            # Parse source range (e.g., "A2:D2")
            start_col, start_row, end_col, end_row = self._parse_a1_range(source_range)
            
            # Create source and destination ranges
            source_range = {
                "sheetId": sheet_id,
                "startRowIndex": start_row - 1,  # Convert to 0-based index
                "endRowIndex": end_row,  # Exclusive end
                "startColumnIndex": self._column_letter_to_index(start_col),
                "endColumnIndex": self._column_letter_to_index(end_col) + 1  # Exclusive end
            }
            
            destination_range = {
                "sheetId": sheet_id,
                "startRowIndex": target_row - 1,  # Convert to 0-based index
                "startColumnIndex": self._column_letter_to_index(start_col)
            }
            
            # Create copy paste request
            requests = [{
                "copyPaste": {
                    "source": source_range,
                    "destination": destination_range,
                    "pasteType": "PASTE_NORMAL",
                    "pasteOrientation": "NORMAL"
                }
            }]
            
            # Execute the request using the service
            self.sheets_client.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            logger.info("Copy operation completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error copying cells: {str(e)}")
            return False
            
    def _column_letter_to_index(self, column: str) -> int:
        """Convert column letter to index (A=0, B=1, etc.)."""
        result = 0
        for char in column.upper():
            result = result * 26 + (ord(char) - ord('A'))
        return result
        
    def _parse_a1_range(self, range_str: str) -> tuple:
        """Parse A1 notation range (e.g., 'A2:D2') into components."""
        # Split into start and end cells
        start, end = range_str.split(':')
        
        # Extract column letters and row numbers
        start_col = ''.join(c for c in start if c.isalpha())
        start_row = int(''.join(c for c in start if c.isdigit()))
        end_col = ''.join(c for c in end if c.isalpha())
        end_row = int(''.join(c for c in end if c.isdigit()))
        
        return start_col, start_row, end_col, end_row
