"""Main application file for the Streamlit web application."""
import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import logging
import time
import json
from utils import GoogleSheetsClient
from services import SpreadsheetService, FormService, UIService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize error handlers for unhandled promises
st.set_option('client.showErrorDetails', True)
st.set_option('client.toolbarMode', 'minimal')

# Load environment variables
load_dotenv()

def load_service_account_json():
    """Load service account JSON from file."""
    json_path = 'flash-etching-442206-j6-be4ff873a719.json'
    try:
        if not os.path.exists(json_path):
            logger.error(f"Service account JSON file not found at {json_path}")
            raise ValueError("Service account JSON file not found")
        
        with open(json_path, 'r') as f:
            json_data = json.load(f)
            
        # Validate required fields
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in json_data]
        if missing_fields:
            raise ValueError(f"Missing required fields in service account JSON: {', '.join(missing_fields)}")
        
        logger.info("Successfully loaded service account JSON from file")
        return json.dumps(json_data)
        
    except Exception as e:
        logger.error(f"Error loading service account JSON: {str(e)}")
        raise ValueError(f"Failed to load service account credentials: {str(e)}")

# Set service account JSON in environment
os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = load_service_account_json()

# Configure page
st.set_page_config(
    page_title="Instapp",
    page_icon="📊",
    layout="wide"
)

def main():
    logger.debug("Starting main application")
    
    # Check for admin access
    is_admin = "admin" in st.experimental_get_query_params()
    
    # Initialize services
    if 'sheets_client' not in st.session_state:
        try:
            logger.info("Initializing Google Sheets client")
            st.session_state.sheets_client = GoogleSheetsClient()
            st.session_state.spreadsheet_service = SpreadsheetService(st.session_state.sheets_client)
            st.session_state.form_service = FormService(st.session_state.sheets_client)
            st.session_state.ui_service = UIService()
            logger.info("Services initialized successfully")
        except Exception as e:
            st.error(f"Failed to initialize services: {str(e)}")
            st.info("Please check your service account credentials and try again.")
            st.stop()
    
    # Display title and connection status
    st.title("📊 Instapp")
    UIService.display_connection_status(st.session_state.sheets_client.connection_status)
    
    # Initialize session state
    if 'spreadsheets' not in st.session_state:
        st.session_state.spreadsheets = []
    if 'selected_sheet' not in st.session_state:
        st.session_state.selected_sheet = None
    
    # Spreadsheet selection section
    st.header("Spreadsheet Selection")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        try:
            if not st.session_state.spreadsheets:
                with st.spinner("Loading spreadsheets..."):
                    st.session_state.spreadsheets = st.session_state.spreadsheet_service.list_spreadsheets()
            
            if not st.session_state.spreadsheets:
                st.warning("📝 No spreadsheets available")
                st.info("""
                    Possible reasons:
                    - Service account has no access to any spreadsheets
                    - No spreadsheets exist in the account
                    - Connection issues with Google API
                """)
            else:
                selected_sheet = st.selectbox(
                    "Select a spreadsheet",
                    options=st.session_state.spreadsheets,
                    format_func=lambda x: x['name'],
                    key='sheet_selector'
                )
                
                if selected_sheet:
                    st.session_state.selected_sheet = selected_sheet
                    st.success(f"Selected: {selected_sheet['name']}")
                    st.info(f"Spreadsheet ID: {selected_sheet['id']}")
        except Exception as e:
            logger.error(f"Error in spreadsheet selection: {str(e)}")
            st.error("⚠️ Error loading spreadsheets")
    
    with col2:
        st.write("")
        st.write("")
        if st.button("🔄 Refresh List"):
            st.session_state.spreadsheets = []
            st.rerun()
    
    # Display sheet data if spreadsheet is selected
    if st.session_state.selected_sheet:
        selected_sheet = st.session_state.selected_sheet
        
        st.subheader("Sheet Details")
        try:
            metadata = st.session_state.spreadsheet_service.get_sheet_metadata(selected_sheet['id'])
            sheets = metadata.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]
            
            selected_sheet_name = st.selectbox(
                "Select sheet",
                options=sheet_names,
                key='sheet_name_selector'
            )
            
            if selected_sheet_name:
                st.subheader("Sheet Data")
                df = st.session_state.spreadsheet_service.read_sheet_data(
                    selected_sheet['id'],
                    selected_sheet_name
                )
                
                UIService.display_sheet_data(df)
                UIService.display_data_quality_report(df)
                
                # Handle INPUTS sheet special case
                if selected_sheet_name == 'INPUTS':
                    st.subheader("📝 Dynamic Form")
                    try:
                        field_name, current_value = st.session_state.form_service.get_input_field_data(
                            selected_sheet['id']
                        )
                        
                        if field_name and current_value is not None:
                            with st.form("dynamic_form"):
                                numeric_value, display_value = st.session_state.form_service.process_input_value(
                                    current_value
                                )
                                
                                if numeric_value is not None:
                                    input_value = st.number_input(
                                        field_name,
                                        value=numeric_value,
                                        format="%.2f" if isinstance(display_value, str) and '%' in display_value else None,
                                        step=0.01 if isinstance(display_value, str) and '%' in display_value else 1.0
                                    )
                                else:
                                    input_value = st.text_input(field_name, value=str(current_value))
                                
                                if st.form_submit_button("Calculate"):
                                    success = st.session_state.spreadsheet_service.update_input_cell(
                                        selected_sheet['id'],
                                        display_value
                                    )
                                    if success:
                                        st.success("✅ Calculation complete! Updated cell B3")
                                        st.rerun()
                        else:
                            st.warning("No data found in cells A2 and B2. Please ensure the INPUTS sheet has data in these cells.")
                    except Exception as e:
                        logger.error(f"Error processing INPUTS sheet: {str(e)}")
                        st.error(f"⚠️ Failed to process INPUTS sheet: {str(e)}")
                
                # Admin-only CSV upload section
                if is_admin:
                    st.subheader("📤 Data Upload")
                    with st.expander("Upload CSV Data"):
                        st.info("Upload a CSV file to replace the current sheet data")
                        uploaded_file = st.file_uploader("Choose CSV file", type="csv", key='csv_uploader')
                        
                        if uploaded_file is not None:
                            try:
                                new_df = pd.read_csv(uploaded_file)
                                st.success("CSV file read successfully!")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("CSV Rows", new_df.shape[0])
                                with col2:
                                    st.metric("CSV Columns", new_df.shape[1])
                                
                                st.write("Preview of uploaded data:")
                                st.dataframe(new_df.head())
                                
                                if st.button("📤 Confirm Upload", key='confirm_upload'):
                                    success = st.session_state.spreadsheet_service.upload_csv_data(
                                        selected_sheet['id'],
                                        selected_sheet_name,
                                        new_df
                                    )
                                    if success:
                                        st.success("✅ Data successfully uploaded!")
                                        st.info("Refreshing page to show updated data...")
                                        time.sleep(2)
                                        st.rerun()
                            except Exception as e:
                                logger.error(f"Error processing CSV upload: {str(e)}")
                                st.error(f"⚠️ Upload failed: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error processing spreadsheet: {str(e)}")
            st.error(f"⚠️ Error: {str(e)}")

if __name__ == "__main__":
    main()