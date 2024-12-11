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

            # Initialize services with retry logic
            import time
            retries = 3
            for attempt in range(retries):
                try:
                    self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
                    self.drive_service = build('drive', 'v3', credentials=self.credentials)
                    status['connected'] = True
                    logger.info("Successfully connected to Google Sheets and Drive APIs")
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}. Retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise

        except Exception as e:
            error_msg = f"Failed to initialize Google Sheets client: {str(e)}"
            status['error'] = error_msg
            logger.error(error_msg)
            raise ValueError(error_msg)

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

    def read_spreadsheet(self, spreadsheet_id: str, range_name: str, value_render_option: str = 'FORMATTED_VALUE') -> pd.DataFrame:
        """Read data from a spreadsheet range with support for various data structures."""
        if not self.connection_status['connected']:
            raise ConnectionError("Google Sheets client is not properly connected")

        try:
            logger.debug(f"Fetching data from spreadsheet {spreadsheet_id}, range: {range_name}")
            # Get values with proper rendering option
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption=value_render_option
            ).execute()
            
            # Extract values from the response
            values = result.get('values', [])
            if not values:
                logger.warning(f"No data found for range {range_name}")
                return pd.DataFrame()

            # Convert to DataFrame directly
            df = pd.DataFrame(values)
            
            # Use first row as headers if available
            if not df.empty:
                df.columns = df.iloc[0]
                df = df[1:].reset_index(drop=True)
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
                valueInputOption='USER_ENTERED',
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