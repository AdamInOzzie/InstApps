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
    """Load service account JSON from environment."""
    service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    
    if not service_account_json:
        logger.error("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set")
        raise ValueError("Service account credentials are missing. Please set GOOGLE_SERVICE_ACCOUNT_JSON environment variable.")
    
    try:
        # Validate JSON from environment variable
        json.loads(service_account_json)
        logger.info("Successfully loaded service account JSON from environment")
        return service_account_json
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in environment variable: {str(e)}")
        raise ValueError("Invalid service account JSON format. Please check your credentials.")

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
                                    
                
                # Dynamic form generation from INPUTS sheet
                if selected_sheet_name == 'INPUTS':
                    st.subheader("📝 Dynamic Form")
                    try:
                        # Read specific cells from INPUTS sheet
                        inputs_range = "INPUTS!A2:B2"  # Read A2 and B2
                        cell_data = st.session_state.sheets_client.read_spreadsheet(selected_sheet['id'], inputs_range)
                        
                        if not cell_data.empty:
                            field_name = cell_data.iloc[0, 0]  # A2 value
                            current_value = cell_data.iloc[0, 1]  # B2 value
                            
                            # Create form
                            with st.form("dynamic_form"):
                                try:
                                    # Handle numeric input, including percentage values
                                    if isinstance(current_value, str) and '%' in current_value:
                                        numeric_value = float(current_value.strip('%')) / 100
                                        input_value = st.number_input(
                                            field_name,
                                            value=numeric_value,
                                            format="%.2f",
                                            step=0.01,
                                            key="input_value"
                                        )
                                        display_value = f"{input_value * 100:.2f}%"
                                    elif isinstance(current_value, (int, float)) or (
                                        isinstance(current_value, str) and current_value.replace('.', '').isdigit()
                                    ):
                                        numeric_value = float(current_value)
                                        input_value = st.number_input(
                                            field_name,
                                            value=numeric_value,
                                            key="input_value"
                                        )
                                        display_value = str(input_value)
                                    else:
                                        input_value = st.text_input(
                                            field_name,
                                            value=str(current_value),
                                            key="input_value"
                                        )
                                        display_value = input_value
                                    
                                    # Calculate button
                                    if st.form_submit_button("Calculate"):
                                        try:
                                            # Update B3 with the calculated value
                                            update_range = "INPUTS!B3"
                                            if st.session_state.sheets_client.write_to_spreadsheet(
                                                selected_sheet['id'],
                                                update_range,
                                                [[display_value]]  # Single cell update
                                            ):
                                                st.success("✅ Calculation complete! Updated cell B3")
                                                logger.info("Successfully updated cell B3")
                                                st.rerun()
                                        except Exception as e:
                                            logger.error(f"Failed to update cell B3: {str(e)}")
                                            st.error("⚠️ Failed to update calculation")
                                            st.error(f"Error: {str(e)}")
                                except ValueError as e:
                                    logger.error(f"Error converting value for {field_name}: {str(e)}")
                                    st.error(f"Invalid value for {field_name}")
                        else:
                            st.warning("No data found in cells A2 and B2. Please ensure the INPUTS sheet has data in these cells.")
                            
                    except Exception as e:
                        logger.error(f"Error processing INPUTS sheet: {str(e)}")
                        st.error("⚠️ Failed to process INPUTS sheet")
                        st.error(f"Error: {str(e)}")
                
                except Exception as e:
                    logger.error(f"Error loading sheet data: {str(e)}")
                    st.error("⚠️ Failed to load sheet data")
                    st.error(f"Error: {str(e)}")
                    st.info("Please check your permissions and try again")

if __name__ == "__main__":
    main()
