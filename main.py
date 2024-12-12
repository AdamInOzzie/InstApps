"""Main application file for the Streamlit web application."""
import streamlit as st

# Configure page with improved layout settings (must be first Streamlit command)
st.set_page_config(
    page_title="Instapp",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",  # Default to collapsed sidebar
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

import os
from dotenv import load_dotenv
import datetime
from datetime import datetime
import time
import psutil
import sys
import traceback
import pandas as pd
import logging
import json
import random  # Added for jitter calculation
from utils import GoogleSheetsClient
from services import SpreadsheetService, FormService, UIService, FormBuilderService, CopyService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Version stamp for deployment verification
VERSION = "2024-12-07-v2"
logger.info("=" * 60)
logger.info("APPLICATION DEPLOYMENT VERIFICATION")
logger.info("=" * 60)
logger.info(f"Version: {VERSION}")
logger.info("Timestamp: " + datetime.now().isoformat())
logger.info("=" * 60)

# Additional startup logging
logger.info("Starting application initialization")

# Load environment variables
load_dotenv()

def load_service_account_json():
    """Load service account JSON from environment variable."""
    try:
        # Get the service account JSON from environment variable
        service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            logger.error("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set")
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set")

        # Parse and validate JSON structure
        try:
            parsed_json = json.loads(service_account_json)
            logger.info("Service account JSON parsed successfully")
            
            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [field for field in required_fields if field not in parsed_json]
            
            if missing_fields:
                error_msg = f"Missing required fields in service account JSON: {', '.join(missing_fields)}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            if parsed_json['type'] != 'service_account':
                error_msg = "Invalid credential type. Expected 'service_account'"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            logger.info(f"Service account email: {parsed_json.get('client_email')}")
            logger.info(f"Project ID: {parsed_json.get('project_id')}")
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format in service account credentials: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Successfully loaded and validated service account JSON")
        return service_account_json

    except Exception as e:
        logger.error(f"Error loading service account JSON: {str(e)}")
        raise ValueError(f"Failed to load service account credentials: {str(e)}")

# Set service account JSON in environment
os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = load_service_account_json()

# Initialize error handlers for unhandled promises
st.set_option('client.showErrorDetails', True)
st.set_option('client.toolbarMode', 'minimal')

# Initialize start time for uptime tracking
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

# Store query parameters in session state for consistent access
if 'query_params' not in st.session_state:
    st.session_state.query_params = {
        'admin': "admin" in st.query_params,
        'healthcheck': "healthcheck" in st.query_params
    }

# Control sidebar visibility
show_sidebar = st.session_state.query_params['admin'] or st.session_state.query_params['healthcheck']

# Apply sidebar visibility CSS
if not show_sidebar:
    st.markdown(
        """
        <style>
            section[data-testid="stSidebar"] {
                display: none !important;
                width: 0px !important;
                height: 0px !important;
                margin: 0px !important;
                padding: 0px !important;
                opacity: 0 !important;
                visibility: hidden !important;
                z-index: -1 !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

def check_user_access(sheet_id: str, username: str) -> bool:
    """Check if username exists in USERS sheet."""
    try:
        # Use cached metadata if available
        metadata_key = f'metadata_{sheet_id}'
        if metadata_key not in st.session_state:
            metadata = st.session_state.spreadsheet_service.get_sheet_metadata(sheet_id)
            if not metadata:
                logger.error("Failed to fetch metadata")
                return True
            st.session_state[metadata_key] = metadata
        
        metadata = st.session_state[metadata_key]
        sheets = metadata.get('sheets', [])
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        
        if 'USERS' not in sheet_names:
            logger.debug("No USERS sheet found in spreadsheet")
            return True
        
        # Read USERS sheet data
        users_df = st.session_state.spreadsheet_service.read_sheet_data(sheet_id, 'USERS')
        if users_df is None or users_df.empty:
            logger.warning("Empty USERS sheet")
            return False
        
        # Check if username exists (case-insensitive)
        return username.lower() in users_df['User Name'].astype(str).str.lower().tolist()
        
    except Exception as e:
        logger.error(f"Error checking user access: {str(e)}")
        if "RATE_LIMIT_EXCEEDED" in str(e):
            st.error("⚠️ Service is temporarily busy. Please try again in a few minutes.")
            return False
        return True  # Fail open on other errors for better user experience

def main():
    # Initialize login state if not exists
    if 'is_logged_in' not in st.session_state:
        st.session_state.is_logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = None
        
    # Handle health check endpoint
    if st.query_params.get("healthcheck"):
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            health_data = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "memory_usage_mb": memory_info.rss / 1024 / 1024,
                "cpu_percent": process.cpu_percent(),
                "uptime_seconds": time.time() - st.session_state.get("start_time", time.time())
            }
            
            st.success("Application is healthy")
            st.json(health_data)
            st.stop()
        except Exception as e:
            st.error(f"Health check failed: {str(e)}")
            st.stop()

    # Custom CSS for form styling
    st.markdown("""
        <style>
        /* Reset Streamlit's default padding */
        .block-container {
            padding: 1rem 0.5rem !important;
            max-width: none !important;
            margin: 0 !important;
        }

        /* Form container styling */
        .stNumberInput, .stTextInput, .stSelectbox {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            display: grid !important;
            grid-template-columns: 250px minmax(200px, 400px) !important;
            align-items: center !important;
            gap: 0.2rem !important;
        }

        /* Mobile responsive layout */
        @media screen and (max-width: 768px) {
            .stNumberInput, .stTextInput, .stSelectbox {
                grid-template-columns: 1fr !important;
                gap: 0.1rem !important;
                margin: 0.1rem 0 !important;
            }
        }

        /* Enhanced label styling */
        .stNumberInput label, .stTextInput label, .stSelectbox label {
            font-weight: 600 !important;
            font-size: 1.1rem !important;
            color: #1E88E5 !important;
            margin: 0 !important;
            padding: 0 !important;
            line-height: 1.5 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            justify-self: start !important;
        }
        
        /* Input field styling */
        .stNumberInput input, .stTextInput input, .stSelectbox select {
            width: 100% !important;
            height: 40px !important;
            border-radius: 6px !important;
            border: 2px solid #E3F2FD !important;
            padding: 0.5rem !important;
            font-size: 1rem !important;
            transition: all 0.2s ease !important;
            margin: 0 !important;
            box-sizing: border-box !important;
            justify-self: start !important;
        }
        
        /* Mobile input adjustments */
        @media screen and (max-width: 768px) {
            .stNumberInput input, .stTextInput input, .stSelectbox select {
                min-width: 0 !important;
                width: 100% !important;
            }
        }
        
        /* Hover and Focus effects */
        .stNumberInput input:hover, .stTextInput input:hover, .stSelectbox select:hover {
            border-color: #90CAF9 !important;
        }
        
        .stNumberInput input:focus, .stTextInput input:focus, .stSelectbox select:focus {
            border-color: #1E88E5 !important;
            box-shadow: 0 1px 4px rgba(30,136,229,0.25) !important;
            outline: none !important;
        }

        /* Container spacing */
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.125rem !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    logger.debug("Starting main application")
    
    # Initialize services
    if 'sheets_client' not in st.session_state:
        try:
            logger.info("Initializing Google Sheets client")
            st.session_state.sheets_client = GoogleSheetsClient()
            st.session_state.spreadsheet_service = SpreadsheetService(st.session_state.sheets_client)
            st.session_state.form_service = FormService(st.session_state.sheets_client)
            st.session_state.form_builder_service = FormBuilderService()
            st.session_state.ui_service = UIService()
            st.session_state.copy_service = CopyService(st.session_state.sheets_client)
            logger.info("Services initialized successfully")
        except Exception as e:
            st.error(f"Failed to initialize services: {str(e)}")
            st.info("Please check your service account credentials and try again.")
            st.stop()
    
    # Display title and health status
    st.title("📊 Instapp")
    
    # Log query parameter status
    logger.info(f"Query parameters: {dict(st.query_params)}")
    logger.info(f"Admin status: {st.session_state.query_params['admin']}, Healthcheck status: {st.session_state.query_params['healthcheck']}")
    
    if st.session_state.query_params['admin'] or st.session_state.query_params['healthcheck']:
        # Show sidebar for admin or healthcheck
        with st.sidebar:
            st.subheader("📡 System Status")
            st.info("Add '?healthcheck' to the URL to view system health")
            if st.button("Check System Health"):
                st.rerun()
        
        # Display admin sidebar if admin parameter is present
        if st.session_state.query_params['admin']:
            UIService.display_admin_sidebar(st.session_state.sheets_client.connection_status)
    
    # Initialize session state variables
    if 'spreadsheets' not in st.session_state:
        st.session_state.spreadsheets = []
    if 'selected_sheet' not in st.session_state:
        st.session_state.selected_sheet = None
    if 'selected_sheet_persisted' not in st.session_state:
        st.session_state.selected_sheet_persisted = None
    
    # Restore selected sheet from persisted state if available
    if st.session_state.is_logged_in and st.session_state.selected_sheet_persisted:
        st.session_state.selected_sheet = st.session_state.selected_sheet_persisted
    
    # App selection section
    col1, col2 = st.columns([4, 1])
    
    with col1:
        try:
            # Load spreadsheets with rate limit handling
            if not st.session_state.spreadsheets:
                with st.spinner("Loading spreadsheets..."):
                    max_retries = 3
                    base_delay = 1
                    
                    for attempt in range(max_retries):
                        try:
                            st.session_state.spreadsheets = st.session_state.spreadsheet_service.list_spreadsheets()
                            break
                        except Exception as e:
                            if "RATE_LIMIT_EXCEEDED" in str(e):
                                if attempt < max_retries - 1:
                                    delay = base_delay * (2 ** attempt)
                                    st.error(f"⚠️ Rate limit exceeded. Retrying in {delay} seconds...")
                                    time.sleep(delay)
                                    continue
                            raise e
            
            # Handle empty spreadsheets list
            if not st.session_state.spreadsheets:
                st.warning("📝 No spreadsheets available")
                st.info("""
                    Possible reasons:
                    - Service account has no access to any spreadsheets
                    - No spreadsheets exist in the account
                    - Connection issues with Google API
                """)
            else:
                # Handle spreadsheet selection with rate limit retry
                max_retries = 3
                base_delay = 1
                
                for attempt in range(max_retries):
                    try:
                        selected_sheet = st.selectbox(
                            "Pick an Instapp",
                            options=st.session_state.spreadsheets,
                            format_func=lambda x: x['name'],
                            key='sheet_selector'
                        )
                        # Clear login state if switching sheets
                        if ('current_sheet_id' not in st.session_state or 
                            st.session_state.get('current_sheet_id') != selected_sheet['id']):
                            st.session_state.is_logged_in = False
                            st.session_state.username = None
                            st.session_state.current_sheet_id = selected_sheet['id']
                        break
                    except Exception as e:
                        if "RATE_LIMIT_EXCEEDED" in str(e):
                            if attempt < max_retries - 1:
                                delay = base_delay * (2 ** attempt)
                                st.error(f"⚠️ Rate limit exceeded. Retrying in {delay} seconds...")
                                time.sleep(delay)
                                continue
                        raise e
                
                if selected_sheet:
                    # Store the selected sheet in session state
                    st.session_state.selected_sheet = selected_sheet
                    if st.session_state.query_params['admin']:
                        st.info(f"Spreadsheet ID: {selected_sheet['id']}")
                    
                    # Check for USERS sheet and handle login
                    try:
                        metadata = st.session_state.spreadsheet_service.get_sheet_metadata(selected_sheet['id'])
                        sheets = metadata.get('sheets', [])
                        sheet_names = [sheet['properties']['title'] for sheet in sheets]
                        
                        has_users_sheet = 'USERS' in sheet_names
                        logger.debug(f"Has USERS sheet: {has_users_sheet}")
                        
                        # For sheets with USERS tab, require login before showing any content
                        if has_users_sheet:
                            if not st.session_state.is_logged_in:
                                st.markdown("🔒 Login Required")
                                username = st.text_input("Enter your username", key="login_username")
                                # Stop here until logged in
                                if not username:
                                    st.stop()
                                if username:
                                    if check_user_access(selected_sheet['id'], username):
                                        st.session_state.is_logged_in = True
                                        st.session_state.username = username
                                        st.session_state.selected_sheet = selected_sheet
                                        st.success("✅ Login successful!")
                                        st.rerun()
                                    else:
                                        st.session_state.is_logged_in = False
                                        st.session_state.username = None
                                        st.session_state.selected_sheet = None
                                        st.error("❌ Access denied. Please check your username.")
                                        st.stop()
                                st.stop()
                        elif not has_users_sheet:
                            # No USERS sheet, allow access
                            st.session_state.is_logged_in = True
                            
                    except Exception as e:
                        logger.error(f"Error checking USERS sheet: {str(e)}")
                        if st.session_state.query_params['admin']:
                            st.error(f"Error checking USERS sheet: {str(e)}")
                        # On error, allow access
                        st.session_state.is_logged_in = True
        except Exception as e:
            logger.error(f"Error in spreadsheet selection: {str(e)}")
            st.error("⚠️ Error loading spreadsheets")
    
    # Add pull-to-refresh functionality
    st.markdown("""
        <script>
            // Pull-to-refresh functionality
            let touchStart = 0;
            let touchEnd = 0;
            
            document.addEventListener('touchstart', function(e) {
                touchStart = e.touches[0].clientY;
            });
            
            document.addEventListener('touchend', function(e) {
                touchEnd = e.changedTouches[0].clientY;
                if (touchStart < touchEnd && window.scrollY === 0) {
                    // User pulled down at top of page
                    window.location.reload();
                }
            });

            // For desktop - mousewheel support
            document.addEventListener('wheel', function(e) {
                if (window.scrollY === 0 && e.deltaY < -50) {
                    // User scrolled up significantly at top of page
                    window.location.reload();
                }
            });
        </script>
    """, unsafe_allow_html=True)
    
    # Display sheet data if spreadsheet is selected
    if st.session_state.selected_sheet:
        selected_sheet = st.session_state.selected_sheet
        
        try:
            metadata = st.session_state.spreadsheet_service.get_sheet_metadata(selected_sheet['id'])
            sheets = metadata.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]
            
            # Check for special sheets
            has_inputs = 'INPUTS' in sheet_names
            has_outputs = 'OUTPUTS' in sheet_names
            
            # Display INPUTS form if it exists
            if has_inputs:
                inputs_df = st.session_state.spreadsheet_service.read_sheet_data(
                    selected_sheet['id'],
                    'INPUTS'
                )
                
                # Process INPUTS form - always visible for all users
                try:
                    fields = st.session_state.form_service.get_input_field_data(
                        selected_sheet['id']
                    )
                    
                    if fields:
                        # Add a visual indicator for inputs section
                        st.markdown("""
                            <div style="
                                background-color: #f0f8ff;
                                padding: 0.5rem 0.8rem;
                                border-radius: 8px;
                                border-left: 5px solid #1E88E5;
                                margin-bottom: 0.6rem;
                            ">
                                <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">⚙️ Inputs</h3>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        for row_idx, (field_name, current_value) in enumerate(fields, start=2):
                            numeric_value, display_value = st.session_state.form_service.process_input_value(
                                current_value
                            )
                            
                            if numeric_value is not None:
                                # Determine step size based on value
                                if isinstance(display_value, str) and '%' in display_value:
                                    step_size = 0.01  # Keep percentage steps small
                                else:
                                    step_size = 0.01 if numeric_value < 10 else 1.0  # More precise control under 10
                                    
                                def create_callback(row):
                                    def callback():
                                        try:
                                            value = st.session_state[f"input_{row}"]
                                            logger.info(f"Raw input value: {value} (type: {type(value)})")
                                            
                                            # Get current value to determine if it's a percentage
                                            current_value = st.session_state.form_service.get_input_field_data(
                                                selected_sheet['id']
                                            )
                                            current_field_value = None
                                            for field_name, field_value in current_value:
                                                if isinstance(field_value, str) and '%' in field_value:
                                                    current_field_value = field_value
                                                    break
                                            
                                            # Format value based on current field type
                                            if current_field_value and '%' in current_field_value:
                                                formatted_value = f"{float(value):.4f}"
                                            else:
                                                formatted_value = str(value)
                                            
                                            logger.info(f"Updating cell B{row} with formatted value: {formatted_value}")
                                            
                                            success = st.session_state.spreadsheet_service.update_input_cell(
                                                selected_sheet['id'],
                                                formatted_value,
                                                row
                                            )
                                            
                                            if not success:
                                                st.error(f"Failed to update cell B{row}")
                                                logger.error(f"Failed to update cell B{row} with value {formatted_value}")
                                            else:
                                                logger.info(f"Successfully updated cell B{row} with value {formatted_value}")
                                                time.sleep(0.5)  # Brief pause to allow update to complete
                                                st.rerun()  # Refresh to show updated values
                                                
                                        except Exception as e:
                                            logger.error(f"Error in update callback: {str(e)}")
                                            st.error(f"Error updating value: {str(e)}")
                                    return callback

                                # Determine format based on value and type
                                format_str = None
                                if isinstance(display_value, str) and '%' in display_value:
                                    format_str = "%.2f"  # Keep percentages at 2 decimal places
                                elif numeric_value < 10:
                                    format_str = "%.3f"  # 3 decimal places for values under 10
                                else:
                                    format_str = "%.2f"  # 2 decimal places for larger values
                                
                                input_value = st.number_input(
                                    field_name,
                                    value=numeric_value,
                                    format=format_str,
                                    step=step_size,
                                    key=f"input_{row_idx}",
                                    on_change=create_callback(row_idx)
                                )
                            else:
                                input_value = st.text_input(
                                    field_name,
                                    value=str(current_value),
                                    key=f"input_{row_idx}"
                                )
                    else:
                        st.warning("No data found in INPUTS sheet. Please ensure the sheet has data.")
                except Exception as e:
                    logger.error(f"Error processing INPUTS sheet: {str(e)}")
                    st.error(f"⚠️ Failed to process INPUTS sheet: {str(e)}")
                
                # Log available sheets for debugging
            logger.info(f"Available sheets: {sheet_names}")
            
            # Check for special sheets
            has_volunteers = 'Volunteers' in sheet_names
            logger.info(f"Has Volunteers sheet: {has_volunteers}")
            
            # Display OUTPUTS data if it exists
            if has_outputs:
                logger.info("Displaying OUTPUTS sheet data")
                outputs_df = st.session_state.spreadsheet_service.read_sheet_data(
                    selected_sheet['id'],
                    'OUTPUTS'
                )
                UIService.display_sheet_data(outputs_df, sheet_type='outputs')
            
            # Add TESTCopy button if Volunteers sheet exists (regardless of OUTPUTS)
            if has_volunteers:
                logger.info("Attempting to display TESTCopy button")
                UIService.display_copy_test_button(selected_sheet['id'], st.session_state.copy_service)
                logger.info("TESTCopy button display completed")
            else:
                logger.info("Skipping TESTCopy button - Volunteers sheet not found")
            
            # Check for USERS sheet and get allowed sheets for the current user
            has_users_sheet = 'USERS' in sheet_names
            allowed_sheets = []
            
            # Add debug logging
            logger.info(f"Has USERS sheet: {has_users_sheet}")
            logger.info(f"Current username: {st.session_state.get('username')}")
            logger.info(f"Is logged in: {st.session_state.get('is_logged_in')}")
            
            if has_users_sheet and st.session_state.get('is_logged_in', False):
                try:
                    users_df = st.session_state.spreadsheet_service.read_sheet_data(
                        selected_sheet['id'],
                        'USERS'
                    )
                    logger.info(f"Users sheet columns: {users_df.columns.tolist()}")
                    
                    if not users_df.empty:
                        username = st.session_state.username.lower()
                        user_row = users_df[users_df['User Name'].str.lower() == username]
                        logger.info(f"Found user row: {not user_row.empty}")
                        
                        # Try both column names
                        append_col = None
                        for col in ['AppendAll', 'APPENDALL', 'Appendall']:
                            if col in users_df.columns:
                                append_col = col
                                break
                        
                        if not user_row.empty and append_col:
                            append_permissions = user_row[append_col].iloc[0]
                            logger.info(f"Append permissions: {append_permissions}")
                            
                            if not pd.isna(append_permissions):
                                allowed_sheets = [s.strip() for s in str(append_permissions).split(',')]
                                logger.info(f"Allowed sheets: {allowed_sheets}")
                                
                                # Create Add button and dropdown for allowed sheets
                                if allowed_sheets:
                                    st.markdown("### Add New Entry")
                                    selected_append_sheet = st.selectbox(
                                        "Add an entry for:",
                                        options=allowed_sheets,
                                        key='append_sheet_selector'
                                    )
                                    
                                    # Handle form generation and submission for selected sheet
                                    if selected_append_sheet:
                                        st.session_state.ui_service.handle_append_entry(
                                            selected_sheet['id'],
                                            selected_append_sheet,
                                            st.session_state.sheets_client,
                                            st.session_state.form_builder_service
                                        )
                except Exception as e:
                    logger.error(f"Error reading USERS sheet: {str(e)}")
                    if is_admin:
                        st.error(f"Error reading USERS sheet: {str(e)}")
            
            # Show data view options
            show_options = st.checkbox("Show additional options", value=False, key='show_options_checkbox')
            if show_options:
                # Filter out special sheets and ensure USERS is always hidden
                available_sheets = [s for s in sheet_names if s not in ['INPUTS', 'OUTPUTS', 'USERS']]
                
                if available_sheets:
                    selected_sheet_name = st.selectbox(
                        "Select sheet to view",
                        options=available_sheets,
                        key='view_sheet_selector'
                    )
                    
                    # Display selected sheet data
                    if selected_sheet_name:
                        df = st.session_state.spreadsheet_service.read_sheet_data(
                            selected_sheet['id'],
                            selected_sheet_name
                        )
                        UIService.display_sheet_data(df, sheet_type='general')
                        if is_admin:
                            UIService.display_data_quality_report(df)
                        df = st.session_state.spreadsheet_service.read_sheet_data(
                            selected_sheet['id'],
                            selected_sheet_name
                        )
                        UIService.display_sheet_data(df, sheet_type='general')
                        if is_admin:
                            UIService.display_data_quality_report(df)
                else:
                    st.info("No additional sheets available for viewing.")
                
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
    try:
        main()
    except Exception as e:
        st.error("⚠️ Application Error")
        st.error(str(e))
        if "admin" in st.query_params:
            st.code(traceback.format_exc())
        logger.error(f"Application error: {str(e)}")
        logger.error(traceback.format_exc())