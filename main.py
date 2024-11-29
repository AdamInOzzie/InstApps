import os
from dotenv import load_dotenv
from utils import GoogleSheetsClient
import streamlit as st
import pandas as pd
import logging
import time
import json

# Initialize error handlers for unhandled promises
st.set_option('client.showErrorDetails', True)
st.set_option('client.toolbarMode', 'minimal')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables before starting Streamlit
load_dotenv()

def load_service_account_json():
    """Load service account JSON from environment or file."""
    service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    
    if service_account_json:
        try:
            # Validate JSON from environment variable
            json.loads(service_account_json)
            logger.info("Successfully loaded service account JSON from environment variable")
            return service_account_json
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in environment variable: {str(e)}")
            logger.info("Falling back to JSON file")
    else:
        logger.info("GOOGLE_SERVICE_ACCOUNT_JSON not set, attempting to load from file")
    
    try:
        with open('flash-etching-442206-j6-be4ff873a719.json', 'r') as f:
            try:
                # Load and validate JSON from file
                json_content = f.read()
                json_obj = json.loads(json_content)
                
                # Convert to single-line JSON string
                formatted_json = json.dumps(json_obj, separators=(',', ':'))
                logger.info("Successfully loaded and formatted service account JSON from file")
                return formatted_json
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                logger.error(f"Error at line {e.lineno}, column {e.colno}: {e.msg}")
                raise ValueError(f"Invalid JSON in service account file: {str(e)}")
    except FileNotFoundError:
        logger.error("Service account JSON file not found")
        raise ValueError("Service account JSON file not found")
    except Exception as e:
        logger.error(f"Unexpected error reading service account file: {str(e)}")
        raise ValueError(f"Error reading service account JSON file: {str(e)}")

# Set service account JSON in environment
os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = load_service_account_json()

# Configure page
st.set_page_config(
    page_title="Instapp",
    page_icon="📊",
    layout="wide"
)

def display_connection_status(status: dict):
    """Display detailed connection status in the sidebar."""
    with st.sidebar:
        st.subheader("System Status")
        
        # Connection status with timestamp
        st.markdown("**API Connection**")
        if status['connected']:
            st.success("✅ Connected to Google Sheets API")
            st.text("Services: Sheets & Drive APIs")
        else:
            st.error("❌ Not connected to Google Sheets API")
            st.text("Unable to access Google APIs")
        
        # Authentication status with details
        st.markdown("**Authentication**")
        if status['authenticated']:
            st.success("✅ Service Account Authenticated")
            st.text("Using Google Service Account")
        else:
            st.error("❌ Authentication failed")
            st.text("Check service account credentials")
        
        # Scopes and permissions
        st.markdown("**Permissions**")
        st.text("• Spreadsheets (Read/Write)")
        st.text("• Drive Metadata (Read)")
        
        # Display error if any
        if status['error']:
            st.markdown("**Error Details**")
            st.error(f"{status['error']}")
            st.text("Check logs for more information")
            
        st.divider()

# Initialize session state
if 'sheets_client' not in st.session_state:
    try:
        logger.info("Initializing Google Sheets client")
        st.session_state.sheets_client = GoogleSheetsClient()
        logger.info("Google Sheets client initialized successfully")
    except ValueError as e:
        st.error(f"Configuration Error: {str(e)}")
        st.info("Please check your service account credentials and try again.")
        st.stop()
    except Exception as e:
        st.error(f"Failed to initialize Google Sheets client: {str(e)}")
        st.info("Check the logs for more details.")
        logger.error(f"Initialization error: {str(e)}")
        st.stop()

def main():
    logger.debug("Starting main application")
    
    # Check for admin access
    is_admin = "admin" in st.experimental_get_query_params()
    
    # Always display the title
    st.title("📊 Instapp")
    
    # Always display connection status
    display_connection_status(st.session_state.sheets_client.connection_status)
    
    # Initialize session state for spreadsheets
    if 'spreadsheets' not in st.session_state:
        logger.debug("Initializing spreadsheets session state")
        st.session_state.spreadsheets = []
    if 'selected_sheet' not in st.session_state:
        logger.debug("Initializing selected sheet session state")
        st.session_state.selected_sheet = None

    # Always display the header
    st.header("Spreadsheet Selection")
    
    # Create columns for layout
    col1, col2 = st.columns([4, 1])
    
    with col1:
        # Load spreadsheets list
        if not st.session_state.spreadsheets:
            try:
                with st.spinner("Loading spreadsheets..."):
                    logger.debug("Attempting to fetch spreadsheets list")
                    st.session_state.spreadsheets = st.session_state.sheets_client.list_spreadsheets()
                    logger.info(f"Successfully loaded {len(st.session_state.spreadsheets)} spreadsheets")
            except Exception as e:
                logger.error(f"Failed to list spreadsheets: {str(e)}")
                st.error("⚠️ Failed to load spreadsheets")
                st.info("Please check your permissions and try again")
                # Don't return here, allow UI to continue rendering
        
        # Display spreadsheet selection or appropriate message
        if not st.session_state.spreadsheets:
            st.warning("📝 No spreadsheets available")
            st.info("""
                Possible reasons:
                - Service account has no access to any spreadsheets
                - No spreadsheets exist in the account
                - Connection issues with Google API
            """)
        else:
            try:
                selected_sheet = st.selectbox(
                    "Select a spreadsheet",
                    options=st.session_state.spreadsheets,
                    format_func=lambda x: x['name'],
                    key='sheet_selector'
                )
                
                if selected_sheet:
                    logger.debug(f"User selected spreadsheet: {selected_sheet['name']} (ID: {selected_sheet['id']})")
                    st.session_state.selected_sheet = selected_sheet
                    st.success(f"Selected: {selected_sheet['name']}")
                    st.info(f"Spreadsheet ID: {selected_sheet['id']}")
            except Exception as e:
                logger.error(f"Error in spreadsheet selection UI: {str(e)}")
                st.error("⚠️ Error displaying spreadsheet selection")
                # Don't return, allow rest of UI to render
    
    with col2:
        st.write("")  # Add some spacing
        st.write("")  # Add some spacing
        if st.button("🔄 Refresh List"):
            logger.debug("User requested spreadsheet list refresh")
            st.session_state.spreadsheets = []
            st.rerun()

    # Main content area
    if st.session_state.selected_sheet:
        selected_sheet = st.session_state.selected_sheet
        logger.debug(f"Processing selected spreadsheet: {selected_sheet['name']}")
        
        # Always show the sheet details section header
        st.subheader("Sheet Details")
        
        # Get spreadsheet metadata
        metadata = None
        try:
            with st.spinner("Loading spreadsheet details..."):
                logger.debug(f"Fetching metadata for spreadsheet: {selected_sheet['id']}")
                metadata = st.session_state.sheets_client.get_spreadsheet_metadata(selected_sheet['id'])
                sheets = metadata.get('sheets', [])
                sheet_names = [sheet['properties']['title'] for sheet in sheets]
                logger.info(f"Found {len(sheets)} sheets in spreadsheet")
        except Exception as e:
            logger.error(f"Failed to load spreadsheet metadata: {str(e)}")
            st.error("⚠️ Failed to load spreadsheet details")
            st.info("Please check if you still have access to this spreadsheet")
            return
        
        # Sheet selection - only show if metadata was successfully loaded
        if metadata:
            selected_sheet_name = st.selectbox(
                "Select sheet",
                options=sheet_names,
                key='sheet_name_selector'
            )
            
            if selected_sheet_name:
                logger.debug(f"User selected sheet: {selected_sheet_name}")
                
                # Data loading section
                st.subheader("Sheet Data")
                
                try:
                    with st.spinner("Loading sheet data..."):
                        range_name = f"{selected_sheet_name}!A1:Z1000"
                        logger.debug(f"Reading data from range: {range_name}")
                        df = st.session_state.sheets_client.read_spreadsheet(selected_sheet['id'], range_name)
                        logger.info(f"Successfully loaded data: {df.shape[0]} rows, {df.shape[1]} columns")
                    
                    # Data display section
                    if df.empty:
                        if not df.columns.empty:
                            st.info("ℹ️ This sheet only contains headers")
                            st.write("Available columns:", df.columns.tolist())
                        else:
                            st.info("ℹ️ This sheet is completely empty")
                    else:
                        # Data statistics
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Total Rows", df.shape[0])
                        with col2:
                            st.metric("Total Columns", df.shape[1])
                        
                        # Calculate column widths based on content
                        column_configs = {col: st.column_config.Column(
                            width="auto"
                        ) for col in df.columns}
                        
                        # Display the data with customized column widths
                        st.dataframe(
                            df,
                            use_container_width=True,
                            column_config=column_configs,
                            hide_index=False
                        )
                        
                        # Data quality information
                        null_counts = df.isnull().sum()
                        has_nulls = null_counts.any()
                        
                        if has_nulls:
                            with st.expander("📊 Data Quality Report"):
                                st.warning("Some columns have missing values:")
                                for col in df.columns:
                                    null_rows = df[df[col].isnull()].index.tolist()
                                    if null_rows:
                                        percentage = (len(null_rows) / len(df)) * 100
                                        st.write(f"- {col}: {len(null_rows)} missing values ({percentage:.1f}%)")
                                        st.write(f"  Missing in rows: {', '.join(map(str, null_rows))}")
                
                    # Data modification section
                    if is_admin:
                        st.subheader("📤 Data Upload")
                        
                        # CSV upload section
                        with st.expander("Upload CSV Data"):
                            st.info("Upload a CSV file to replace the current sheet data")
                            uploaded_file = st.file_uploader("Choose CSV file", type="csv", key='csv_uploader')
                            
                            if uploaded_file is not None:
                                logger.debug(f"Processing uploaded CSV file: {uploaded_file.name}")
                                
                                try:
                                    # Read and validate CSV
                                    new_df = pd.read_csv(uploaded_file)
                                    logger.debug(f"Successfully read CSV: {new_df.shape[0]} rows, {new_df.shape[1]} columns")
                                    
                                    # Display upload information
                                    st.success("CSV file read successfully!")
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.metric("CSV Rows", new_df.shape[0])
                                    with col2:
                                        st.metric("CSV Columns", new_df.shape[1])
                                    
                                    # Preview data
                                    st.write("Preview of uploaded data:")
                                    st.dataframe(new_df.head())
                                    
                                    # Upload confirmation
                                    if st.button("📤 Confirm Upload", key='confirm_upload'):
                                        try:
                                            with st.spinner("Uploading data to Google Sheets..."):
                                                logger.debug("Converting DataFrame to values list")
                                                values = [new_df.columns.tolist()] + new_df.values.tolist()
                                                
                                                logger.debug(f"Writing data to sheet: {range_name}")
                                                if st.session_state.sheets_client.write_to_spreadsheet(
                                                    selected_sheet['id'],
                                                    range_name,
                                                    values
                                                ):
                                                    logger.info("Successfully uploaded data to sheet")
                                                    st.success("✅ Data successfully uploaded!")
                                                    st.info("Refreshing page to show updated data...")
                                                    time.sleep(2)  # Give user time to read the message
                                                    st.rerun()
                                        except Exception as e:
                                            logger.error(f"Failed to upload data: {str(e)}")
                                            st.error("⚠️ Upload failed!")
                                            st.error(f"Error: {str(e)}")
                                            st.info("Please check your permissions and try again")
                                
                                except pd.errors.EmptyDataError:
                                    logger.warning("Uploaded CSV file is empty")
                                    st.warning("The uploaded CSV file is empty")
                                except Exception as e:
                                    logger.error(f"Failed to read CSV file: {str(e)}")
                                    st.error("⚠️ Failed to read CSV file")
                                    st.error(f"Error: {str(e)}")
                                    st.info("Please ensure your CSV file is properly formatted")
                
                except Exception as e:
                    logger.error(f"Error loading sheet data: {str(e)}")
                    st.error("⚠️ Failed to load sheet data")
                    st.error(f"Error: {str(e)}")
                    st.info("Please check your permissions and try again")

if __name__ == "__main__":
    main()
