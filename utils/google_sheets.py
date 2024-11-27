import json
import os
import logging
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleSheetsClient:
    def __init__(self):
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.metadata.readonly'
        ]
        self.credentials = None
        self.sheets_service = None
        self.drive_service = None
        self.connection_status = self._initialize_client()

    def _validate_service_account_json(self, service_account_info: dict) -> bool:
        """Validate service account JSON structure and content."""
        required_fields = [
            'type', 'project_id', 'private_key_id', 'private_key',
            'client_email', 'client_id', 'auth_uri', 'token_uri'
        ]
        
        # Check for required fields
        missing_fields = [field for field in required_fields if field not in service_account_info]
        if missing_fields:
            raise ValueError(f"Missing required fields in service account JSON: {', '.join(missing_fields)}")
            
        # Validate service account type
        if service_account_info['type'] != 'service_account':
            raise ValueError("Invalid service account type. Must be 'service_account'")
            
        # Validate private key format
        if not service_account_info['private_key'].startswith('-----BEGIN PRIVATE KEY-----'):
            raise ValueError("Invalid private key format")
            
        # Validate client email format
        if not service_account_info['client_email'].endswith('.iam.gserviceaccount.com'):
            raise ValueError("Invalid client email format")
            
        return True

    def _initialize_client(self) -> Dict[str, Any]:
        """Initialize Google Sheets client with proper error handling."""
        status = {
            'connected': False,
            'authenticated': False,
            'error': None
        }

        try:
            # Get and validate service account JSON
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set")

            try:
                service_account_info = json.loads(service_account_json)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                logger.error(f"Invalid JSON near position {e.pos}: {e.msg}")
                raise ValueError(f"Failed to parse service account JSON: {str(e)}")

            # Validate the service account JSON structure and content
            self._validate_service_account_json(service_account_info)

            # Initialize credentials
            self.credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=self.scopes
            )
            status['authenticated'] = True
            logger.info("Successfully authenticated with service account")

            # Initialize services
            self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            status['connected'] = True
            logger.info("Successfully connected to Google Sheets and Drive APIs")

        except json.JSONDecodeError:
            error_msg = "Invalid JSON format in service account credentials"
            status['error'] = error_msg
            logger.error(error_msg)
            raise ValueError(error_msg)
        except ValueError as e:
            status['error'] = str(e)
            logger.error(f"Validation error: {str(e)}")
            raise
        except Exception as e:
            error_msg = f"Failed to initialize Google Sheets client: {str(e)}"
            status['error'] = error_msg
            logger.error(error_msg)
            raise

        return status

    def list_spreadsheets(self) -> List[Dict[str, str]]:
        """List all available spreadsheets."""
        if not self.connection_status['connected']:
            raise ConnectionError("Google Sheets client is not properly connected")

        try:
            results = self.drive_service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                fields="files(id, name)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
            spreadsheets = results.get('files', [])
            logger.info(f"Successfully listed {len(spreadsheets)} spreadsheets")
            return spreadsheets
        except HttpError as e:
            error_msg = f"Failed to list spreadsheets: {str(e)}"
            if e.resp.status == 403:
                error_msg = "Permission denied. Please check service account permissions"
            elif e.resp.status == 401:
                error_msg = "Authentication failed. Please check service account credentials"
            logger.error(error_msg)
            raise Exception(error_msg)

    def read_spreadsheet(self, spreadsheet_id: str, range_name: str) -> pd.DataFrame:
        """Read data from a spreadsheet range with support for various data structures."""
        if not self.connection_status['connected']:
            raise ConnectionError("Google Sheets client is not properly connected")

        try:
            logger.debug(f"Fetching data from spreadsheet {spreadsheet_id}, range: {range_name}")
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            # Log the raw API response for debugging
            logger.debug(f"API Response: {json.dumps(result, indent=2)}")
            
            # Check if the response contains the 'values' key
            if 'values' not in result:
                logger.warning(f"API response missing 'values' key for range {range_name}")
                return pd.DataFrame()
            
            values = result['values']
            
            # Log detailed information about the values
            logger.debug(f"Raw values: Number of rows: {len(values)}")
            for i, row in enumerate(values):
                logger.debug(f"Row {i+1}: {row} (Length: {len(row)})")
            
            # Handle completely empty sheet
            if not values:
                logger.warning(f"Sheet is completely empty in range {range_name}")
                return pd.DataFrame()

            # Analyze data structure
            non_empty_rows = [i for i, row in enumerate(values) if row and any(str(cell).strip() for cell in row if cell is not None)]
            if not non_empty_rows:
                logger.warning("No non-empty rows found in the sheet")
                return pd.DataFrame()

            logger.debug(f"Non-empty rows found at positions: {non_empty_rows}")
            
            # Find the maximum width of the data
            max_width = max(len(row) for row in values)
            logger.debug(f"Maximum width of data: {max_width}")

            # Determine if first row is empty or contains headers
            first_row_empty = not values[0] or not any(str(cell).strip() for cell in values[0] if cell is not None)
            logger.debug(f"First row empty: {first_row_empty}")

            # Detect if data is tabular (has meaningful headers)
            def is_tabular_data(first_row):
                if not first_row:
                    return False
                # Check if first row has meaningful text values (not just numbers or empty)
                meaningful_headers = [
                    str(cell).strip() for cell in first_row 
                    if cell and str(cell).strip() and not str(cell).strip().replace('.','').isdigit()
                ]
                return len(meaningful_headers) > len(first_row) / 2

            # Create letter-based column names (A, B, C, ...)
            def get_letter_header(index):
                if index < 26:
                    return chr(65 + index)
                else:
                    # For columns beyond Z (AA, AB, etc.)
                    first = chr(65 + (index // 26) - 1)
                    second = chr(65 + (index % 26))
                    return f"{first}{second}"

            is_tabular = not first_row_empty and is_tabular_data(values[0])
            logger.debug(f"Data structure detected as: {'tabular' if is_tabular else 'non-tabular'}")

            if first_row_empty or not is_tabular:
                logger.debug("Creating letter-based headers (A, B, C, ...)")
                header = [get_letter_header(i) for i in range(max_width)]
                data_start_idx = 0 if first_row_empty else 0
            else:
                # Use first row as headers, pad if necessary with letter-based headers
                header = values[0]
                if len(header) < max_width:
                    logger.debug(f"Padding header row from length {len(header)} to {max_width}")
                    header.extend([get_letter_header(i) for i in range(len(header), max_width)])
                data_start_idx = 1

            # Clean and standardize headers
            header = [get_letter_header(i) if not cell or str(cell).strip() == '' else str(cell).strip() 
                     for i, cell in enumerate(header)]
            logger.debug(f"Final headers: {header}")

            # Process all rows, including empty ones
            data = []
            actual_row_indices = []
            total_rows = len(values)
            
            for i in range(data_start_idx, total_rows):
                actual_row_num = i + 1  # Sheet row number (1-based)
                row = values[i] if i < len(values) else []
                
                # Handle empty rows
                if not row or not any(str(cell).strip() for cell in row if cell is not None):
                    logger.debug(f"Processing empty row at position {actual_row_num}")
                    processed_row = [None] * len(header)
                else:
                    logger.debug(f"Processing row {actual_row_num}: {row}")
                    
                    # Handle row length discrepancies
                    if len(row) != len(header):
                        if len(row) < len(header):
                            logger.debug(f"Padding row {actual_row_num} from length {len(row)} to {len(header)}")
                            row = row + [None] * (len(header) - len(row))
                        else:
                            logger.debug(f"Trimming row {actual_row_num} from length {len(row)} to {len(header)}")
                            row = row[:len(header)]
                    
                    # Process cell values
                    processed_row = []
                    for cell in row:
                        if cell is None or str(cell).strip() == '':
                            processed_row.append(None)
                        else:
                            # Handle percentage values
                            cell_str = str(cell).strip()
                            if cell_str.endswith('%'):
                                try:
                                    value = float(cell_str.rstrip('%')) / 100
                                    processed_row.append(value)
                                    logger.debug(f"Converted percentage value '{cell_str}' to {value}")
                                except ValueError:
                                    processed_row.append(cell_str)
                            else:
                                processed_row.append(cell)

                data.append(processed_row)
                actual_row_indices.append(actual_row_num)
                logger.debug(f"Processed row {actual_row_num}: {processed_row}")

            # Create DataFrame with original sheet row numbers as index
            df = pd.DataFrame(data, columns=header, index=actual_row_indices)
            
            # Log summary statistics
            logger.info(f"Successfully read {len(df)} rows from spreadsheet")
            logger.debug(f"Row indices: {actual_row_indices}")
            logger.debug(f"DataFrame shape: {df.shape}")
            logger.debug(f"Columns: {df.columns.tolist()}")
            logger.debug(f"Missing values per column: {df.isnull().sum().to_dict()}")
            logger.debug(f"Data types per column: {df.dtypes.to_dict()}")
            
            return df
        except HttpError as e:
            error_msg = f"Failed to read spreadsheet: {str(e)}"
            if e.resp.status == 403:
                error_msg = "Permission denied. Please check read permissions for this spreadsheet"
            elif e.resp.status == 404:
                error_msg = "Spreadsheet not found. Please check the spreadsheet ID"
            logger.error(error_msg)
            raise Exception(error_msg)

    def write_to_spreadsheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]) -> bool:
        """Write data to a spreadsheet range."""
        if not self.connection_status['connected']:
            raise ConnectionError("Google Sheets client is not properly connected")

        try:
            body = {'values': values}
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            logger.info(f"Successfully wrote {len(values)} rows to spreadsheet")
            return True
        except HttpError as e:
            error_msg = f"Failed to write to spreadsheet: {str(e)}"
            if e.resp.status == 403:
                error_msg = "Permission denied. Please check write permissions for this spreadsheet"
            elif e.resp.status == 404:
                error_msg = "Spreadsheet not found. Please check the spreadsheet ID"
            logger.error(error_msg)
            raise Exception(error_msg)

    def get_spreadsheet_metadata(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Get metadata about a spreadsheet."""
        if not self.connection_status['connected']:
            raise ConnectionError("Google Sheets client is not properly connected")

        try:
            metadata = self.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            logger.info(f"Successfully retrieved metadata for spreadsheet {spreadsheet_id}")
            return metadata
        except HttpError as e:
            error_msg = f"Failed to get spreadsheet metadata: {str(e)}"
            if e.resp.status == 403:
                error_msg = "Permission denied. Please check permissions for this spreadsheet"
            elif e.resp.status == 404:
                error_msg = "Spreadsheet not found. Please check the spreadsheet ID"
            logger.error(error_msg)
            raise Exception(error_msg)
