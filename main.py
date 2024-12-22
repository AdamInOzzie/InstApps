"""Main application file for the Streamlit web application."""
import streamlit as st
import stripe
from stripe.error import (
    StripeError,
    InvalidRequestError,
    APIConnectionError,
    APIError,
    AuthenticationError,
    CardError,
)

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
    })

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
from services import (SpreadsheetService, FormService, UIService,
                      FormBuilderService, CopyService, PaymentService)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
    """Load service account JSON from file or environment variable with proper escaping."""
    try:
        # Helper function to validate JSON structure
        def validate_json(parsed_json):
            required_fields = [
                'type', 'project_id', 'private_key_id', 'private_key',
                'client_email'
            ]
            missing_fields = [
                field for field in required_fields if field not in parsed_json
            ]

            if missing_fields:
                error_msg = f"Missing required fields in service account JSON: {', '.join(missing_fields)}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if parsed_json['type'] != 'service_account':
                error_msg = "Invalid credential type. Expected 'service_account'"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Validate private key format
            if not parsed_json['private_key'].strip().startswith(
                    '-----BEGIN PRIVATE KEY-----'):
                error_msg = "Invalid private key format"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info(
                f"Service account email: {parsed_json.get('client_email')}")
            logger.info(f"Project ID: {parsed_json.get('project_id')}")
            return parsed_json

        # First try to read from the credentials file
        creds_file = "Pasted--type-service-account-project-id-flash-etching-442206-j6-private-key-id-be4ff-1733997763234.txt"
        if os.path.exists(creds_file):
            logger.info(f"Reading credentials from file: {creds_file}")
            try:
                with open(creds_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Handle potential BOM and normalize line endings
                    content = content.strip().replace('\r\n', '\n')
                    parsed_json = json.loads(content)
            except (IOError, UnicodeError) as e:
                logger.error(f"Error reading credentials file: {str(e)}")
                raise ValueError(f"Failed to read credentials file: {str(e)}")
            except json.JSONDecodeError as je:
                logger.error(f"Failed to parse JSON from file: {str(je)}")
                raise ValueError(
                    f"Invalid JSON in credentials file: {str(je)}")
        else:
            # Fallback to environment variable
            logger.info(
                "Credentials file not found, checking environment variable")
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                logger.error(
                    "No credentials found in file or environment variable")
                raise ValueError(
                    "No credentials found in file or environment variable")

            try:
                # Clean the JSON string before parsing
                service_account_json = service_account_json.strip()
                # Remove any unwanted Unicode characters
                service_account_json = ''.join(
                    char for char in service_account_json
                    if char.isprintable() or char in ['\n', '\r', '\t'])
                parsed_json = json.loads(service_account_json)
            except json.JSONDecodeError as je:
                logger.error(
                    f"Failed to parse JSON from environment: {str(je)}")
                logger.error(
                    f"JSON content preview: {service_account_json[:50]}...")
                raise ValueError(
                    f"Invalid JSON in environment variable: {str(je)}")

        # Validate the JSON structure
        parsed_json = validate_json(parsed_json)

        # Convert back to JSON string with proper escaping
        service_account_json = json.dumps(parsed_json,
                                          ensure_ascii=False,
                                          indent=None,
                                          separators=(',', ':'))
        logger.info("Successfully loaded and validated service account JSON")
        return service_account_json

    except Exception as e:
        logger.error(f"Error loading service account JSON: {str(e)}")
        logger.error(f"Full error details: {traceback.format_exc()}")
        raise ValueError(
            f"Failed to load service account credentials: {str(e)}")


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

# Control sidebar visibility for admin, healthcheck, and successful payments
show_sidebar = (st.session_state.query_params['admin']
                or st.session_state.query_params['healthcheck']
                or ('payment' in st.query_params
                    and st.query_params.get('payment') == 'success'))

# Apply sidebar visibility CSS
if not show_sidebar:
    st.markdown("""
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
                unsafe_allow_html=True)


def check_user_access(sheet_id: str, username: str) -> bool:
    """Check if username exists in USERS sheet."""
    try:
        # Use cached metadata if available
        metadata_key = f'metadata_{sheet_id}'
        if metadata_key not in st.session_state:
            metadata = st.session_state.spreadsheet_service.get_sheet_metadata(
                sheet_id)
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
        users_df = st.session_state.spreadsheet_service.read_sheet_data(
            sheet_id, 'USERS')
        if users_df is None or users_df.empty:
            logger.warning("Empty USERS sheet")
            return False

        # Check if username exists (case-insensitive)
        return username.lower() in users_df['Name'].astype(
            str).str.lower().tolist()

    except Exception as e:
        logger.error(f"Error checking user access: {str(e)}")
        if "RATE_LIMIT_EXCEEDED" in str(e):
            st.error(
                "⚠️ Service is temporarily busy. Please try again in a few minutes."
            )
            return False
        return True  # Fail open on other errors for better user experience


def main():
    # Initialize all required services
    if 'sheets_client' not in st.session_state:
        logger.info("Initializing Google Sheets client")
        st.session_state.sheets_client = GoogleSheetsClient()
        st.session_state.spreadsheet_service = SpreadsheetService(
            st.session_state.sheets_client)
        st.session_state.form_service = FormService(
            st.session_state.sheets_client)
        st.session_state.form_builder_service = FormBuilderService()
        st.session_state.ui_service = UIService()

    # Check for payment callback first
    logger.info("=" * 80)
    logger.info("CHECKING PAYMENT CALLBACK")
    query_params = dict(st.query_params)
    logger.info(f"All query parameters: {query_params}")
    logger.info(f"Raw URL being accessed: {query_params}")
    logger.info("Session and Request Information")
    if hasattr(st, 'session_state'):
        logger.info(f"Session State Keys: {list(st.session_state.keys())}")
    
    if 'payment' in st.query_params and 'session_id' in st.query_params:
        logger.info(f"Payment status: {st.query_params.get('payment')}")
        logger.info(f"Session ID: {st.query_params.get('session_id')}")
        logger.info("Payment callback parameters detected")
        if st.query_params.get('payment') == 'success':
            session_id = st.query_params.get('session_id')
            logger.info("=" * 80)
            logger.info("PAYMENT CALLBACK RECEIVED")
            logger.info(
                f"Processing payment callback for session: {session_id}")
            # Log Stripe session metadata
            logger.info("=" * 80)
            logger.info("STRIPE SESSION METADATA CHECK")
            logger.info(f"Processing payment session ID: {session_id}")
            try:
                stripe_session = stripe.checkout.Session.retrieve(session_id)
                logger.info(f"Retrieved metadata from Stripe session: {stripe_session.metadata}")
                logger.info(f"Spreadsheet ID: {stripe_session.metadata.get('spreadsheet_id')}")
                logger.info(f"Row Number: {stripe_session.metadata.get('row_number')}")
            except Exception as e:
                logger.error(f"Failed to retrieve Stripe session metadata: {str(e)}")
            logger.info("=" * 80)
            logger.info("=" * 80)

            # Initialize essential services for payment verification
            if 'sheets_client' not in st.session_state:
                st.session_state.sheets_client = GoogleSheetsClient()

            try:
                logger.info("=" * 80)
                logger.info("PROCESSING PAYMENT CALLBACK")
                logger.info(f"Session ID: {session_id}")
                
                # Use UI service to handle payment verification and sheet update
                if 'ui_service' not in st.session_state:
                    st.session_state.ui_service = UIService()
                
                logger.info("Calling UI service to verify payment and update sheet")
                verification_result = st.session_state.ui_service.verify_payment_and_submit(session_id, st.session_state.sheets_client)
                
                if verification_result:
                    success_message = "✅ Payment verified and recorded successfully!"
                    logger.info(success_message)
                    st.success(success_message)
                else:
                    error_message = "Failed to verify payment or update record"
                    logger.error(error_message)
                    st.error(error_message)
            except Exception as e:
                logger.error(f"Error processing payment callback: {str(e)}")
                st.error(f"Error processing payment: {str(e)}")

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
                "status":
                "healthy",
                "timestamp":
                datetime.now().isoformat(),
                "memory_usage_mb":
                memory_info.rss / 1024 / 1024,
                "cpu_percent":
                process.cpu_percent(),
                "uptime_seconds":
                time.time() - st.session_state.get("start_time", time.time())
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
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-start !important;
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
        .stNumberInput label, .stTextInput label, .stSelectbox label, .stDateInput label {
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
    """,
                unsafe_allow_html=True)

    logger.debug("Starting main application")

    # Initialize services
    if 'sheets_client' not in st.session_state:
        try:
            logger.info("Initializing Google Sheets client")
            st.session_state.sheets_client = GoogleSheetsClient()
            st.session_state.spreadsheet_service = SpreadsheetService(
                st.session_state.sheets_client)
            st.session_state.form_service = FormService(
                st.session_state.sheets_client)
            st.session_state.form_builder_service = FormBuilderService()
            st.session_state.ui_service = UIService()
            st.session_state.copy_service = CopyService(
                st.session_state.sheets_client)
            try:
                logger.info("Initializing PaymentService...")
                # Check environment variables before initializing
                stripe_secret = os.getenv('STRIPE_SECRET_KEY')
                stripe_publishable = os.getenv('STRIPE_PUBLISHABLE_KEY')

                logger.info("Checking deployment environment variables...")
                logger.info(
                    f"STRIPE_SECRET_KEY present in environment: {bool(stripe_secret)}"
                )
                logger.info(
                    f"STRIPE_PUBLISHABLE_KEY present in environment: {bool(stripe_publishable)}"
                )

                st.session_state.payment_service = PaymentService()
                logger.info("PaymentService initialized successfully")
            except ValueError as e:
                logger.error(f"PaymentService initialization failed: {str(e)}")
                error_msg = str(e)
                st.error(
                    f"⚠️ Payment service configuration error: {error_msg}")

                # More detailed information for debugging
                if st.session_state.query_params.get('admin'):
                    st.info("Admin Note: Environment Variable Status")
                    status_info = {
                        'STRIPE_SECRET_KEY':
                        'Present'
                        if os.getenv('STRIPE_SECRET_KEY') else 'Missing',
                        'STRIPE_PUBLISHABLE_KEY':
                        'Present'
                        if os.getenv('STRIPE_PUBLISHABLE_KEY') else 'Missing'
                    }
                    for key, status in status_info.items():
                        st.code(f"{key}: {status}")
                    st.info(
                        "These environment variables must be properly set in your deployment environment"
                    )
                st.stop()
            except Exception as e:
                logger.error(
                    f"Unexpected error initializing PaymentService: {str(e)}")
                st.error(
                    "⚠️ Unexpected error initializing payment service. Please try again."
                )
                st.stop()

            logger.info("All services initialized successfully")
        except Exception as e:
            st.error(f"Failed to initialize services: {str(e)}")
            st.info(
                "Please check your service account credentials and try again.")
            st.stop()

    # Handle payment status messages
    # Handle payment status from URL parameters
    payment_status = st.query_params.get("payment")
    session_id = st.query_params.get("session_id")

    # Persist login state through payment callback
    if payment_status == "success" and session_id:
        if 'payment_sessions' in st.session_state and session_id in st.session_state.payment_sessions:
            payment_data = st.session_state.payment_sessions[session_id]
            if 'username' in payment_data:
                st.session_state.is_logged_in = True
                st.session_state.username = payment_data['username']
                st.session_state.selected_sheet = payment_data[
                    'selected_sheet']

        try:
            # Initialize Stripe with the secret key
            stripe_key = os.getenv('STRIPE_SECRET_KEY')
            if not stripe_key:
                logger.error("Stripe secret key is missing")
                st.error(
                    "⚠️ Payment verification failed: Missing Stripe configuration"
                )
                return

            stripe.api_key = stripe_key

            try:
                logger.info(
                    f"Starting payment verification for session: {session_id}")
                # Initialize Stripe with retry logic
                max_retries = 3
                retry_count = 0

                while retry_count < max_retries:
                    try:
                        # Verify the payment session with detailed logging
                        session = stripe.checkout.Session.retrieve(session_id)
                        
                        # Log comprehensive session details
                        logger.info("=" * 80)
                        logger.info("STRIPE SESSION DATA VERIFICATION")
                        logger.info("=" * 80)
                        logger.info("Basic Session Info:")
                        logger.info(f"Session ID: {session_id}")
                        logger.info(f"Payment Status: {session.payment_status}")
                        logger.info(f"Amount Total: {session.amount_total}")
                        logger.info(f"Currency: {session.currency}")
                        
                        logger.info("\nMetadata Details:")
                        logger.info(f"Raw Metadata: {session.metadata}")
                        # Check for required metadata fields
                        required_fields = ['spreadsheet_id', 'row_number']
                        missing_fields = [field for field in required_fields if field not in session.metadata]
                        
                        if missing_fields:
                            logger.error(f"Missing required metadata fields: {missing_fields}")
                        else:
                            logger.info("Required Metadata Fields:")
                            logger.info(f"  spreadsheet_id: {session.metadata.get('spreadsheet_id')}")
                            logger.info(f"  row_number: {session.metadata.get('row_number')}")
                            
                        logger.info("\nAll Metadata Fields:")
                        for key, value in session.metadata.items():
                            logger.info(f"  {key}: {value}")
                        
                        logger.info("\nCustomer Details:")
                        if session.customer_details:
                            logger.info(f"Email: {session.customer_details.email}")
                            logger.info(f"Name: {session.customer_details.name if hasattr(session.customer_details, 'name') else 'No name'}")
                        else:
                            logger.info("No customer details available")
                            
                        logger.info("\nPayment Intent Details:")
                        if session.payment_intent:
                            logger.info(f"Payment Intent ID: {session.payment_intent}")
                            try:
                                payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)
                                logger.info(f"Payment Intent Status: {payment_intent.status}")
                                logger.info(f"Payment Method: {payment_intent.payment_method_types}")
                            except Exception as e:
                                logger.error(f"Error retrieving payment intent details: {str(e)}")
                        
                        logger.info("\nComplete Session Object:")
                        logger.info(str(session))
                        logger.info("=" * 80)

                        if session.payment_status == "paid":
                            st.success(
                                "✅ Payment completed successfully! Thank you for your payment."
                            )
                            logger.info(
                                f"Successful payment for session: {session_id}"
                            )

                            # Clear the success parameters after showing the message
                            if 'query_params' in st.session_state:
                                st.session_state.query_params.pop(
                                    'payment', None)
                                st.session_state.query_params.pop(
                                    'session_id', None)
                            break

                        elif session.payment_status == "unpaid":
                            st.warning(
                                "⏳ Payment is being processed. Please wait a moment."
                            )
                            logger.warning(
                                f"Payment pending for session: {session_id}")
                            break
                        else:
                            st.warning(
                                f"Payment status: {session.payment_status}")
                            logger.warning(
                                f"Unexpected payment status for session {session_id}: {session.payment_status}"
                            )
                            break

                    except APIConnectionError as e:
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.warning(
                                f"Connection error, attempt {retry_count} of {max_retries}: {str(e)}"
                            )
                            time.sleep(1 * retry_count)  # Exponential backoff
                            continue
                        logger.error(
                            f"Failed to connect to Stripe after {max_retries} attempts: {str(e)}"
                        )
                        st.error(
                            "⚠️ Unable to verify payment status. Please refresh the page or try again later."
                        )
                        return

                    except APIError as e:
                        logger.error(f"Stripe API error: {str(e)}")
                        st.error(
                            "⚠️ Unable to process payment verification. Please try again later."
                        )
                        return

            except InvalidRequestError as e:
                logger.error(f"Invalid Stripe session ID: {str(e)}")
                st.error("⚠️ Invalid payment session. Please try again.")
                return

            except AuthenticationError as e:
                logger.error(f"Stripe authentication error: {str(e)}")
                st.error(
                    "⚠️ Payment verification failed due to authentication error."
                )
                return

            except CardError as e:
                logger.error(f"Card error: {str(e)}")
                st.error(
                    f"⚠️ Card error: {e.user_message if hasattr(e, 'user_message') else str(e)}"
                )
                return

            except StripeError as e:
                logger.error(f"Stripe error verifying payment: {str(e)}")
                st.error(
                    f"⚠️ Payment verification failed: {e.user_message if hasattr(e, 'user_message') else str(e)}"
                )
                return

            except Exception as e:
                logger.error(
                    f"Unexpected error during payment verification: {str(e)}")
                logger.error(f"Full error details: {traceback.format_exc()}")
                st.error(
                    "⚠️ An unexpected error occurred. Please try again or contact support."
                )
                return

        except Exception as e:
            logger.error(f"Error verifying payment session: {str(e)}")
            logger.error(f"Full error details: {traceback.format_exc()}")
            st.error(
                "⚠️ Unable to verify payment status. Please try again or contact support."
            )
    elif payment_status == "cancelled":
        st.warning("Payment was cancelled. You can try again when ready.")
        logger.info("Payment cancelled by user")

    # Display title and health status
    st.title("📊 Instapp")

    # Log query parameter status
    logger.info(f"Query parameters: {dict(st.query_params)}")
    logger.info(
        f"Admin status: {st.session_state.query_params['admin']}, Healthcheck status: {st.session_state.query_params['healthcheck']}"
    )

    if st.session_state.query_params['admin'] or st.session_state.query_params[
            'healthcheck']:
        # Show sidebar for admin or healthcheck
        with st.sidebar:
            st.subheader("📡 System Status")
            st.info("Add '?healthcheck' to the URL to view system health")
            if st.button("Check System Health", key="health_check_1"):
                st.rerun()

        # Display admin sidebar if admin parameter is present
        if st.session_state.query_params['admin']:
            with st.sidebar:
                st.subheader("📡 System Status")
                st.info("Add '?healthcheck' to the URL to view system health")
                if st.button("Check System Health", key="health_check_2"):
                    st.rerun()

                # Payment Test Section
                st.markdown("---")
                st.subheader("💳 Payment Testing")
                if st.checkbox("Show Payment Form",
                               value=False,
                               key='admin_payment_test'):
                    st.markdown("### Make a Test Payment")
                    payment_amount = st.number_input(
                        "Amount ($)",
                        min_value=0.5,
                        value=10.0,
                        step=0.5,
                        key='admin_payment_amount')

                    # Add test data input fields
                    test_row_number = st.number_input("Test Row Number", min_value=1, value=1)
                    test_sheet_id = st.text_input("Test Sheet ID", value=st.session_state.get('selected_sheet', ''))
                    
                    if st.button("Process Payment",
                                 key='admin_process_payment'):
                        try:
                            # Initialize payment_sessions if not exists
                            if 'payment_sessions' not in st.session_state:
                                st.session_state.payment_sessions = {}

                            # Store test values in session state
                            st.session_state.current_row_number = test_row_number
                            st.session_state.current_sheet_id = test_sheet_id
                            st.session_state.selected_sheet = test_sheet_id

                            # Get required data from session state with explicit logging
                            current_row = test_row_number
                            selected_sheet = test_sheet_id
                            
                            # Log session state for debugging
                            logger.info("=" * 80)
                            logger.info("PAYMENT SESSION STATE CHECK")
                            logger.info(f"Current Row: {current_row}")
                            logger.info(f"Selected Sheet: {selected_sheet}")
                            logger.info(f"Session State Keys: {list(st.session_state.keys())}")
                            logger.info(f"current_sheet_id: {st.session_state.get('current_sheet_id')}")
                            logger.info(f"selected_sheet: {st.session_state.get('selected_sheet')}")
                            logger.info("=" * 80)
                            
                            # Validate required data
                            if not current_row:
                                st.error("Missing row number for payment processing")
                                logger.error("Missing row number in session state")
                                return
                            
                            if not selected_sheet:
                                st.error("No spreadsheet selected for payment processing")
                                logger.error("Missing spreadsheet ID in session state")
                                return
                                
                            logger.info("=" * 80)
                            logger.info("CREATING PAYMENT INTENT")
                            logger.info(f"Spreadsheet ID: {selected_sheet}")
                            logger.info(f"Row Number: {current_row}")
                            logger.info(f"Amount: {payment_amount}")
                            logger.info("=" * 80)
                            
                            # Create payment intent with spreadsheet details
                            payment_data = st.session_state.payment_service.create_payment_intent(
                                amount=payment_amount,
                                spreadsheet_id=selected_sheet,
                                row_number=current_row)

                            if 'error' in payment_data:
                                st.error(
                                    f"Payment Error: {payment_data['error']}")
                            else:
                                # Store payment data in session state with complete context
                                st.session_state.payment_intent_data = payment_data
                                
                                # Store payment session data with full context
                                logger.info("=" * 80)
                                logger.info("STORING PAYMENT SESSION")
                                logger.info(f"Session ID being stored: {payment_data['session_id']}")
                                logger.info(f"Spreadsheet ID: {st.session_state.selected_sheet}")
                                logger.info(f"Row Number: {current_row}")
                                
                                # Store complete context in session state
                                st.session_state.payment_sessions[payment_data['session_id']] = {
                                    'amount': payment_amount,
                                    'spreadsheet_id': st.session_state.selected_sheet,
                                    'row_number': current_row,
                                    'created_at': datetime.now().isoformat(),
                                    'status': 'pending'
                                }
                                
                                # Show payment success message
                                st.success(
                                    f"Payment session created successfully!\n\n"
                                    f"Amount: ${payment_amount:.2f}")

                                # Show Stripe Checkout link
                                st.markdown(
                                    f"[Complete Payment on Stripe]({payment_data['session_url']})"
                                )
                                
                                logger.info(f"Updated payment sessions: {st.session_state.payment_sessions}")
                                logger.info("=" * 80)

                        except Exception as e:
                            st.error(f"Error processing payment: {str(e)}")

                # Display other admin tools
                UIService.display_admin_sidebar(
                    st.session_state.sheets_client.connection_status)

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
                            st.session_state.spreadsheets = st.session_state.spreadsheet_service.list_spreadsheets(
                            )
                            break
                        except Exception as e:
                            if "RATE_LIMIT_EXCEEDED" in str(e):
                                if attempt < max_retries - 1:
                                    delay = base_delay * (2**attempt)
                                    st.error(
                                        f"⚠️ Rate limit exceeded. Retrying in {delay} seconds..."
                                    )
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
                            key='sheet_selector')
                        # Clear login state if switching sheets
                        if ('current_sheet_id' not in st.session_state
                                or st.session_state.get('current_sheet_id')
                                != selected_sheet['id']):
                            st.session_state.is_logged_in = False
                            st.session_state.username = None
                            st.session_state.current_sheet_id = selected_sheet[
                                'id']
                        break
                    except Exception as e:
                        if "RATE_LIMIT_EXCEEDED" in str(e):
                            if attempt < max_retries - 1:
                                delay = base_delay * (2**attempt)
                                st.error(
                                    f"⚠️ Rate limit exceeded. Retrying in {delay} seconds..."
                                )
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
                        metadata = st.session_state.spreadsheet_service.get_sheet_metadata(
                            selected_sheet['id'])
                        sheets = metadata.get('sheets', [])
                        sheet_names = [
                            sheet['properties']['title'] for sheet in sheets
                        ]

                        has_users_sheet = 'USERS' in sheet_names
                        logger.debug(f"Has USERS sheet: {has_users_sheet}")

                        # For sheets with USERS tab, require login before showing any content
                        if has_users_sheet:
                            if not st.session_state.is_logged_in:
                                st.markdown("🔒 Login Required")
                                username = st.text_input("Enter your username",
                                                         key="login_username")
                                # Stop here until logged in
                                if not username:
                                    st.stop()
                                if username:
                                    if check_user_access(
                                            selected_sheet['id'], username):
                                        st.session_state.is_logged_in = True
                                        st.session_state.username = username
                                        st.session_state.selected_sheet = selected_sheet
                                        st.success("✅ Login successful!")
                                        st.rerun()
                                    else:
                                        st.session_state.is_logged_in = False
                                        st.session_state.username = None
                                        st.session_state.selected_sheet = None
                                        st.error(
                                            "❌ Access denied. Please check your username."
                                        )
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
    """,
                unsafe_allow_html=True)

    # Initialize NewEntriesForms service if not exists

    # Display sheet data if spreadsheet is selected
    if st.session_state.selected_sheet:
        selected_sheet = st.session_state.selected_sheet

        try:
            metadata = st.session_state.spreadsheet_service.get_sheet_metadata(
                selected_sheet['id'])
            sheets = metadata.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]

            # Check for special sheets
            has_inputs = 'INPUTS' in sheet_names
            has_outputs = 'OUTPUTS' in sheet_names

            # Display INPUTS form if it exists
            if has_inputs:
                inputs_df = st.session_state.spreadsheet_service.read_sheet_data(
                    selected_sheet['id'], 'INPUTS')
                # Process INPUTS form
                try:
                    st.session_state.form_service.handle_inputs_sheet(
                        selected_sheet['id'])
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
                    selected_sheet['id'], 'OUTPUTS')
                UIService.display_sheet_data(outputs_df, sheet_type='outputs')

            # Check for USERS sheet and get allowed sheets for the current user
            has_users_sheet = 'USERS' in sheet_names
            allowed_sheets = []

            # Add debug logging
            logger.info(f"Has USERS sheet: {has_users_sheet}")
            logger.info(
                f"Current username: {st.session_state.get('username')}")
            logger.info(
                f"Is logged in: {st.session_state.get('is_logged_in')}")

            if has_users_sheet and st.session_state.get('is_logged_in', False):
                try:
                    users_df = st.session_state.spreadsheet_service.read_sheet_data(
                        selected_sheet['id'], 'USERS')
                    logger.info(
                        f"Users sheet columns: {users_df.columns.tolist()}")

                    if not users_df.empty:
                        username = st.session_state.username.lower()
                        user_row = users_df[users_df['Name'].str.lower() ==
                                            username]
                        logger.info(f"Found user row: {not user_row.empty}")

                        # Try both column names
                        append_col = None
                        for col in ['AppendAll', 'APPENDALL', 'Appendall']:
                            if col in users_df.columns:
                                append_col = col
                                break

                        if not user_row.empty and append_col:
                            append_permissions = user_row[append_col].iloc[0]
                            logger.info(
                                f"Append permissions: {append_permissions}")

                            if not pd.isna(append_permissions):
                                allowed_sheets = [
                                    s.strip()
                                    for s in str(append_permissions).split(',')
                                ]
                                logger.info(
                                    f"Allowed sheets: {allowed_sheets}")

                                # Create dropdown for allowed sheets with larger font
                                if allowed_sheets:
                                    selected_append_sheet = st.selectbox(
                                        "Add an entry for:",
                                        options=allowed_sheets,
                                        key='append_sheet_selector',
                                        label_visibility="visible")
                                    # Apply custom styling to the label
                                    st.markdown("""
                                        <style>
                                            div[data-testid="stSelectbox"] label {
                                                font-size: 1.3rem !important;
                                                font-weight: 600 !important;
                                                color: #1E88E5 !important;
                                            }
                                        </style>
                                    """,
                                                unsafe_allow_html=True)

                                    # Handle form generation and submission for selected sheet
                                    if selected_append_sheet:
                                        st.session_state.ui_service.handle_append_entry(
                                            selected_sheet['id'],
                                            selected_append_sheet,
                                            st.session_state.sheets_client, st.
                                            session_state.form_builder_service)
                except Exception as e:
                    logger.error(f"Error reading USERS sheet: {str(e)}")
                    if UIService.is_admin():
                        st.error(f"Error reading USERS sheet: {str(e)}")

            # Show data view options with proper sheet selection
            selected_sheet_name = st.session_state.get('append_sheet_selector',
                                                       '')
            show_options = st.checkbox(
                f"Show {selected_sheet_name}", value=False,
                key='show_options_checkbox')
            if show_options:
                # Get list of available sheets excluding special sheets
                available_sheets = [
                    s for s in sheet_names
                    if s not in ['INPUTS', 'OUTPUTS', 'USERS']
                ]

                if not available_sheets:
                    st.info("No additional sheets available for viewing.")
                    return

                # If there's only one sheet, use it directly
                if len(available_sheets) == 1:
                    selected_sheet_name = available_sheets[0]
                # If we have an active dynamic entry form, use its selected sheet
                elif st.session_state.get('append_sheet_selector'):
                    selected_sheet_name = st.session_state.append_sheet_selector
                # Otherwise show sheet selector
                else:
                    selected_sheet_name = st.selectbox(
                        "Select sheet to view:",
                        options=available_sheets,
                        key='view_sheet_selector')

                if selected_sheet_name:
                    try:
                        # Read data from the selected sheet
                        logger.info(
                            f"Reading data from sheet: {selected_sheet_name}")
                        df = st.session_state.spreadsheet_service.read_sheet_data(
                            selected_sheet['id'], selected_sheet_name)
                        if df is not None:
                            logger.info(
                                f"Data read successfully. Shape: {df.shape}, Columns: {df.columns.tolist()}"
                            )
                            logger.info(f"DataFrame info: {df.info()}")

                        # Display the data if available
                        if df is not None and not df.empty:
                            # Display the DataFrame

                            UIService.display_sheet_data(df,
                                                         sheet_type='general')

                            # Show data quality report for admins
                            if UIService.is_admin():
                                UIService.display_data_quality_report(df)
                        else:
                            st.warning(
                                f"No data available in sheet '{selected_sheet_name}'"
                            )

                    except Exception as e:
                        st.error(f"Error displaying sheet data: {str(e)}")
                        logger.error(f"Error in display_sheet_data: {str(e)}")
                else:
                    st.info("No additional sheets available for viewing.")

                # Admin-only CSV upload section
                if UIService.is_admin():
                    st.subheader("📤 Data Upload")
                    with st.expander("Upload CSV Data"):
                        st.info(
                            "Upload a CSV file to replace the current sheet data"
                        )
                        uploaded_file = st.file_uploader("Choose CSV file",
                                                         type="csv",
                                                         key='csv_uploader')

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

                                if st.button("📤 Confirm Upload",
                                             key='confirm_upload'):
                                    success = st.session_state.spreadsheet_service.upload_csv_data(
                                        selected_sheet['id'],
                                        selected_sheet_name, new_df)
                                    if success:
                                        st.success(
                                            "✅ Data successfully uploaded!")
                                        st.info(
                                            "Refreshing page to show updated data..."
                                        )
                                        time.sleep(2)
                                        st.rerun()
                            except Exception as e:
                                logger.error(
                                    f"Error processing CSV upload: {str(e)}")
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
