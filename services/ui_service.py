"""Service for handling UI components and displays."""
import logging
import streamlit as st
import pandas as pd
from services.copy_service import CopyService
from services.form_builder_service import FormBuilderService
from typing import Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class UIService:
    @staticmethod
    def is_admin() -> bool:
        """Check if current user has admin privileges."""
        return 'admin' in st.query_params
    @staticmethod
    def format_output_value(value_str: str, field_name: str) -> str:
        """Format output values while preserving original formatting."""
        try:
            # Remove any commas from the original string
            original_value = str(value_str).strip()
            
            # If it's already a properly formatted value, return as is
            if original_value.startswith('$') or original_value.endswith('%'):
                return original_value
                
            # Check if it's a currency value (should have $ prefix)
            if "Portfolio" in field_name:
                clean_value = original_value.replace('$', '').replace(',', '')
                try:
                    float_value = float(clean_value)
                    return f"${float_value:,.0f}"
                except ValueError:
                    return original_value
                    
            # Check if it's a percentage/allocation value
            if "Allocation" in field_name or "Rate" in field_name:
                try:
                    clean_value = original_value.replace('%', '').replace('$', '').replace(',', '').strip()
                    float_value = float(clean_value)
                    if float_value <= 1:  # Decimal format (e.g., 0.59)
                        float_value *= 100
                    return f"{float_value:.0f}%"
                except ValueError:
                    return original_value
                    
            return original_value
            
        except Exception as e:
            logger.error(f"Error formatting output value: {str(e)}")
            return value_str

    @staticmethod
    def verify_payment_and_submit(session_id: str, sheets_client) -> bool:
        """Verify payment and submit form if successful."""
        try:
            # Entry point logging
            logger.info("="*80)
            logger.info("CHECKING PAYMENT CALLBACK")
            logger.info("="*80)

            # Log payment verification attempt
            logger.info(f"Starting payment verification for session: {session_id}")
            logger.info(f"Current query parameters: {dict(st.query_params)}")
            logger.info(f"Available session state keys: {list(st.session_state.keys())}")

            # Log all URL parameters and session state
            logger.info("="*80)
            logger.info("PAYMENT CALLBACK PARAMETERS")
            logger.info(f"All query parameters: {dict(st.query_params)}")
            logger.info(f"Raw session ID from parameter: {session_id}")
            logger.info(f"Current URL path: {st.runtime.get_instance()._get_url_path()}")
            logger.info(f"Payment sessions in state: {list(st.session_state.payment_sessions.keys()) if 'payment_sessions' in st.session_state else 'None'}")
            logger.info("="*80)

            # Initialize payment service and verify payment status
            try:
                from services.payment_service import PaymentService
                payment_service = PaymentService()
                
                # Get payment status from Stripe
                payment_status = payment_service.get_payment_status(session_id)
                logger.info("Payment status retrieved:")
                logger.info(json.dumps(payment_status, indent=2))

                # Extract metadata for sheet update
                metadata = payment_status.get('metadata', {})
                spreadsheet_id = metadata.get('spreadsheet_id')
                row_number = int(metadata.get('row_number', 0))

                if not spreadsheet_id or not row_number:
                    logger.error("Missing required metadata")
                    return False

            # Initialize payment_sessions if not exists
            if 'payment_sessions' not in st.session_state:
                st.session_state.payment_sessions = {}
                logger.info("Initialized empty payment_sessions in session state")
            
            # Get the stored session data if it exists
            stored_session = st.session_state.payment_sessions.get(session_id)
            logger.info(f"Retrieved stored session data: {stored_session}")
            
            # If no stored session, try to proceed with metadata from callback
            if not stored_session:
                logger.info("No stored session found, will use metadata from callback")

            # Log session data details
            logger.info("="*80)
            logger.info("VERIFYING PAYMENT SESSION")
            logger.info(f"Session ID: {session_id}")
            logger.info(f"Payment Sessions: {list(st.session_state.payment_sessions.keys()) if 'payment_sessions' in st.session_state else 'None'}")
            logger.info("="*80)

            try:
                # Get payment status from Stripe
                logger.info("="*80)
                logger.info("INITIALIZING STRIPE PAYMENT SERVICE")
                logger.info("="*80)
                
                from services.payment_service import PaymentService
                from services.spreadsheet_service import SpreadsheetService
                payment_service = PaymentService()
                
                logger.info("="*80)
                logger.info("RETRIEVING STRIPE SESSION IN CALLBACK")
                logger.info(f"Session ID: {session_id}")
                logger.info("Attempting to retrieve payment status...")
                
                try:
                    payment_status = payment_service.get_payment_status(session_id)
                    logger.info("Successfully retrieved payment status")
                    logger.info("Full payment status response:")
                    logger.info("="*80)
                    logger.info(json.dumps(payment_status, indent=2))
                    logger.info("="*80)

                    # Extract metadata for sheet update
                    metadata = payment_status.get('metadata', {})
                    spreadsheet_id = metadata.get('spreadsheet_id')
                    row_number = int(metadata.get('row_number', 0))

                    if spreadsheet_id and row_number:
                        logger.info(f"Updating sheet {spreadsheet_id} at row {row_number}")
                        
                        # First verify spreadsheet exists and get available sheets
                        from utils.google_sheets import GoogleSheetsClient
                        sheets_client = GoogleSheetsClient()
                        
                        try:
                            # Get spreadsheet metadata to verify sheets
                            sheet_metadata = sheets_client.get_spreadsheet_metadata(spreadsheet_id)
                            available_sheets = [sheet['properties']['title'] for sheet in sheet_metadata.get('sheets', [])]
                            logger.info(f"Available sheets: {available_sheets}")
                            
                            if 'Sponsors' not in available_sheets:
                                logger.error("Sponsors sheet not found in spreadsheet")
                                return False
                            
                            # Verify the row exists by reading the sheet
                            df = sheets_client.read_spreadsheet(spreadsheet_id, 'Sponsors!A:H')
                            if df is None or len(df) < row_number:
                                logger.error(f"Row {row_number} not found in Sponsors sheet")
                                return False
                                
                            logger.info(f"Verified row {row_number} exists in sheet with {len(df)} rows")
                            
                            # Prepare and execute the update
                            cell_updates = [row_number, 8, f"PAID_STRIPE_{session_id}"]
                            logger.info(f"Updating cell H{row_number} with: PAID_STRIPE_{session_id}")
                            
                            update_success = SpreadsheetService.UpdateEntryCells(
                                spreadsheet_id=spreadsheet_id,
                                sheet_name='Sponsors',
                                cell_updates=cell_updates
                            )
                            
                            if update_success:
                                logger.info("Successfully updated payment status in sheet")
                                return True
                            else:
                                logger.error("Sheet update failed")
                                return False
                                
                        except Exception as e:
                            logger.error(f"Error during sheet update: {str(e)}")
                            return False
                            
                    else:
                        logger.error("Missing required metadata for sheet update")
                        return False
                        
                except Exception as e:
                    logger.error(f"Error retrieving Stripe session: {str(e)}")
                    return False
                
                if not payment_status or payment_status.get('status') != 'succeeded':
                    logger.warning(f"Payment not successful. Full status: {json.dumps(payment_status, indent=2)}")
                    return False

                # Extract and log metadata from the Stripe session
                metadata = payment_status.get('metadata', {})
                logger.info("="*80)
                logger.info("STRIPE CALLBACK METADATA")
                logger.info(f"Raw metadata: {json.dumps(metadata, indent=2)}")
                logger.info(f"Amount: {metadata.get('amount')} ({metadata.get('amount_cents')} cents)")
                logger.info(f"Payment Status: {metadata.get('payment_status')}")
                logger.info(f"Spreadsheet ID: {metadata.get('spreadsheet_id')}")
                logger.info(f"Row Number: {metadata.get('row_number')}")
                
                # Parse the form_data JSON string from metadata
                import json
                form_data = json.loads(metadata.get('form_data', '{}'))
                logger.info(f"Parsed form data: {form_data}")
                
                # Create session data from the Stripe metadata directly
                session_data = {
                    'spreadsheet_id': metadata.get('spreadsheet_id'),
                    'row_number': int(metadata.get('row_number', 0)),
                    'amount': float(metadata.get('amount', 0)),
                    'sheet_name': 'Sponsors'  # Default to Sponsors sheet
                }
                logger.info("="*80)
                logger.info("SESSION DATA DETAILS")
                logger.info(f"Row Number: {session_data['row_number']}")
                logger.info(f"Sheet Name: {session_data['sheet_name']}")
                logger.info(f"Spreadsheet ID: {session_data['spreadsheet_id']}")
                logger.info(f"Amount: ${session_data['amount']}")
                logger.info(f"Session ID: {session_id}")
                logger.info("="*80)
                
            except Exception as e:
                logger.error(f"Error processing payment metadata: {str(e)}")
                st.error(f"Error processing payment: {str(e)}")
                return False

            try:
                # Initialize GoogleSheetsClient
                from utils.google_sheets import GoogleSheetsClient
                client = GoogleSheetsClient()
                
                # Log session data details
                logger.info("="*80)
                logger.info("SESSION DATA DETAILS")
                logger.info(f"Row Number: {session_data['row_number']}")
                logger.info(f"Sheet Name: {session_data['sheet_name']}")
                logger.info(f"Spreadsheet ID: {session_data['spreadsheet_id']}")
                logger.info(f"Amount: ${session_data['amount']}")
                logger.info(f"Session ID: {session_id}")
                logger.info("="*80)

                # Update the Paid field in the spreadsheet directly
                try:
                    # Update the Paid field in the spreadsheet directly
                    logger.info("="*80)
                    logger.info("ATTEMPTING SPREADSHEET UPDATE")
                    logger.info("="*80)

                    # Import SpreadsheetService
                    try:
                        from services.spreadsheet_service import SpreadsheetService
                        logger.info("Successfully imported SpreadsheetService")
                        
                        # Log detailed session data
                        logger.info("="*80)
                        logger.info("PREPARING CELL UPDATE")
                        logger.info(f"Session Data:")
                        logger.info(f"- Spreadsheet ID: {session_data['spreadsheet_id']}")
                        logger.info(f"- Sheet Name: {session_data['sheet_name']}")
                        logger.info(f"- Row Number: {session_data['row_number']}")
                        logger.info(f"- Amount: ${session_data['amount']}")
                        logger.info(f"- Session ID: {session_id}")
                        
                        # Verify row exists first
                        logger.info("Verifying row exists...")
                        df = sheets_client.read_spreadsheet(
                            session_data['spreadsheet_id'], 
                            f"{session_data['sheet_name']}!A:H"
                        )
                        if df is None or len(df) < session_data['row_number']:
                            logger.error(f"Row {session_data['row_number']} not found in sheet")
                            return False
                            
                        logger.info(f"Row verification successful - Sheet has {len(df)} rows")
                        
                        # Prepare cell updates for the Paid field (Column H)
                        # Convert row number to integer and ensure it's valid
                        row_num = int(session_data['row_number'])
                        logger.info(f"Converting row number {session_data['row_number']} to integer: {row_num}")
                        
                        # Prepare the cell updates array with the correct format
                        cell_updates = [row_num, 8, f"PAID_STRIPE_{session_id}"]
                        logger.info(f"Prepared cell updates array: {cell_updates}")
                        
                        # Log the exact update we're about to perform
                        logger.info(f"Will update sheet '{session_data['sheet_name']}' at row {row_num}, column H with value 'PAID_STRIPE_{session_id}'")
                        logger.info("="*80)
                        logger.info("CELL UPDATE DETAILS")
                        logger.info(f"Row: {cell_updates[0]}")
                        logger.info(f"Column: {cell_updates[1]} (H)")
                        logger.info(f"Value: {cell_updates[2]}")
                        logger.info("="*80)
                        
                        # Use SpreadsheetService's UpdateEntryCells method
                        logger.info("="*80)
                        logger.info("UPDATING GOOGLE SHEET")
                        logger.info("="*80)
                        
                        try:
                            # Log the exact parameters being passed
                            logger.info("UpdateEntryCells Parameters:")
                            logger.info(f"spreadsheet_id: {session_data['spreadsheet_id']}")
                            logger.info(f"sheet_name: {session_data['sheet_name']}")
                            logger.info(f"cell_updates: {cell_updates}")
                            logger.info(f"Row number (pre-conversion): {session_data['row_number']}")
                            logger.info(f"Row number (post-conversion): {row_num}")
                            
                            # Double-check the spreadsheet exists and is accessible
                            sheet_info = sheets_client.get_spreadsheet_metadata(session_data['spreadsheet_id'])
                            if not sheet_info:
                                logger.error("Could not access spreadsheet - metadata lookup failed")
                                return False
                                
                            logger.info(f"Successfully verified spreadsheet access: {sheet_info.get('spreadsheetId')}")
                            
                            # Attempt the update
                            update_success = SpreadsheetService.UpdateEntryCells(
                                spreadsheet_id=session_data['spreadsheet_id'],
                                sheet_name=session_data['sheet_name'],
                                cell_updates=cell_updates
                            )
                            
                            logger.info(f"Update attempt complete - Success: {update_success}")
                            
                            if not update_success:
                                logger.error("UpdateEntryCells returned False but didn't raise an exception")
                                st.error("Failed to update the payment status in the spreadsheet")
                                return False
                                
                        except Exception as update_error:
                            logger.error(f"Error in UpdateEntryCells: {str(update_error)}")
                            logger.error(f"Error type: {type(update_error).__name__}")
                            st.error(f"Failed to update payment status: {str(update_error)}")
                            return False
                        
                        logger.info("="*80)
                        logger.info("UPDATE OPERATION RESULT")
                        logger.info(f"Success: {update_success}")
                        logger.info("="*80)
                    except Exception as e:
                        logger.error(f"Error during spreadsheet update: {str(e)}")
                        logger.error(f"Error type: {type(e).__name__}")
                        return False
                    
                    if update_success:
                        logger.info(f"Successfully updated spreadsheet for session {session_id}")
                        st.success("✅ Payment verified and entry updated successfully!")
                        # Clean up session data
                        if session_id in st.session_state.payment_sessions:
                            del st.session_state.payment_sessions[session_id]
                        st.rerun()
                        return True
                    else:
                        logger.error("Failed to update spreadsheet")
                        st.error("Failed to update spreadsheet")
                        return False
                except Exception as e:
                    logger.error(f"Error updating spreadsheet: {str(e)}")
                    st.error(f"Error updating spreadsheet: {str(e)}")
                    
            except Exception as e:
                    logger.error(f"Error updating spreadsheet: {str(e)}")
                    st.error(f"Error updating spreadsheet: {str(e)}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error verifying payment: {str(e)}")
            st.error(f"Error processing payment: {str(e)}")
            return False


    @staticmethod
    def display_admin_sidebar(status: Dict[str, Any]):
        """Display admin-only information in the sidebar."""
        # Always check for payment success and display in main content
        if 'payment' in st.query_params and 'session_id' in st.query_params:
            if st.query_params.get('payment') == 'success':
                session_id = st.query_params.get('session_id')
                # This section has been moved to verify_payment_and_submit
                pass
        
        with st.sidebar:
                        
            st.subheader("Admin Dashboard")
            
            # Add API Debug section when admin mode is active
            if UIService.is_admin():
                st.markdown("### 🔍 API Debug")
                if 'last_api_call' in st.session_state:
                    st.json(st.session_state.last_api_call)
                else:
                    st.info("No API calls logged yet")
            
            st.markdown("### System Status")
            
            st.markdown("**API Connection**")
            if status['connected']:
                st.success("✅ Connected to Google Sheets API")
                st.text("Services: Sheets & Drive APIs")
            else:
                st.error("❌ Not connected to Google Sheets API")
                st.text("Unable to access Google APIs")
            
            st.markdown("**Authentication**")
            if status['authenticated']:
                st.success("✅ Service Account Authenticated")
                st.text("Using Google Service Account")
            else:
                st.error("❌ Authentication failed")
                st.text("Check service account credentials")
            
            st.markdown("**Permissions**")
            st.text("• Spreadsheets (Read/Write)")
            st.text("• Drive Metadata (Read)")
            
            if status['error']:
                st.markdown("**Error Details**")
                st.error(f"{status['error']}")
                st.text("Check logs for more information")
                
            st.divider()
            
            # Display admin status
            if UIService.is_admin():
                st.success("🔑 Admin Mode Active")
                st.text("Advanced features enabled")
            
            st.divider()

    @staticmethod
    def display_data_quality_report(df: pd.DataFrame):
        """Display data quality information."""
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

    @staticmethod
    def handle_append_entry(spreadsheet_id: str, sheet_name: str, sheets_client, form_builder_service) -> Optional[Dict[str, Any]]:
        """Handle the dynamic form generation and submission for appending entries."""
        try:
            logger.info("=" * 80)
            logger.info("FORM SUBMISSION PROCESS START")
            logger.info("=" * 80)
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Sheet Name: {sheet_name}")
            
            # Read the sheet data to get structure
            range_name = f"{sheet_name}!A1:Z1000"
            logger.info(f"Reading sheet data from {range_name}")
            df = sheets_client.read_spreadsheet(spreadsheet_id, range_name)
            
            logger.info(f"Sheet {sheet_name} data loaded - Shape: {df.shape if df is not None else 'None'}")
            
            # Get form fields and formula fields from sheet structure
            logger.info(f"Generating form fields for sheet {sheet_name}")
            form_fields, formula_fields = form_builder_service.get_form_fields(
                df,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            )
            
            if not form_fields and not formula_fields:
                st.warning(f"Could not generate form fields from sheet '{sheet_name}'")
                logger.error(f"No form fields or formula fields generated for sheet {sheet_name}")
                return None
                
            # Store formula fields in session state
            if 'formula_fields' not in st.session_state:
                st.session_state.formula_fields = {}
            st.session_state.formula_fields[sheet_name] = formula_fields
            
            # Render the form with sheet name and sheets client
            form_data = form_builder_service.render_form(form_fields, sheet_name, spreadsheet_id=spreadsheet_id, sheets_client=sheets_client)
            
            # Log form data for debugging
            logger.info("Form Data Generated:")
            for field_name, value in form_data.items():
                logger.info(f"Field: {field_name} = {value} (type: {type(value)})")
            
            # Add submit button with proper error handling
            if st.button("Submit Entry", type="primary"):
                logger.info("Submit button clicked - Processing form submission")
                result = UIService._handle_form_submission(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    sheets_client=sheets_client,
                    form_data=form_data
                )
                logger.info(f"Form submission result: {result}")
                return result
            
            return form_data
            
        except Exception as e:
            logger.error(f"Error handling append entry: {str(e)}")
            st.error(f"Error generating form: {str(e)}")
            return None
            
    @staticmethod
    def _handle_form_submission(
        spreadsheet_id: str,
        sheet_name: str,
        sheets_client,
        form_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle form submission with payment processing if required."""
        logger.info("=" * 80)
        logger.info("FORM SUBMISSION HANDLER")
        logger.info("=" * 80)
        logger.info(f"Processing submission for sheet: {sheet_name}")
        logger.info(f"Form data received: {form_data}")
        
        try:
            from services.spreadsheet_service import SpreadsheetService
            
            # First, append the entry
            entry_range = f"{sheet_name}!A:A"
            entry_df = sheets_client.read_spreadsheet(spreadsheet_id, entry_range)
            next_row = int(2 if entry_df.empty else entry_df[entry_df.columns[0]].notna().sum() + 2)
            
            # Create copy service and execute copy operation
            copy_service = CopyService(sheets_client)
            source_range = f"{sheet_name}!A2:Z2"
            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                source_range=source_range,
                target_row=next_row
            )
            
            if not success:
                st.error("Failed to copy entry template")
                return None

            # Update cells with form data
            cell_updates = []
            df = sheets_client.read_spreadsheet(spreadsheet_id, f"{sheet_name}!A1:Z1000")
            form_fields, _ = FormBuilderService().get_form_fields(df, spreadsheet_id, sheet_name)
            
            for field_name, value in form_data.items():
                field_info = next((f for f in form_fields if f['name'] == field_name), None)
                if field_info:
                    column_index = field_info['column_index'] + 1
                    cell_updates.extend([next_row, column_index, str(value)])
            
            update_success = SpreadsheetService.UpdateEntryCells(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                cell_updates=cell_updates
            )
            
            if not update_success:
                st.error("Failed to update entry values")
                return None

            # Now check if payment is required
            payment_amount = None
            if 'Price' in form_data and 'QTY' in form_data:
                try:
                    price = float(form_data['Price'])
                    qty = float(form_data['QTY'])
                    payment_amount = price * qty
                    if payment_amount > 0:
                        logger.info("=" * 80)
                        logger.info("INITIATING PAYMENT PROCESS")
                        logger.info(f"Spreadsheet ID: {spreadsheet_id}")
                        logger.info(f"Sheet Name: {sheet_name}")
                        logger.info(f"Row Number: {next_row}")
                        logger.info(f"Payment Amount: {payment_amount}")
                        logger.info("=" * 80)

                        # Create payment intent using PaymentService with required parameters
                        from services.payment_service import PaymentService
                        payment_service = PaymentService()
                        payment_data = payment_service.create_payment_intent(
                            amount=payment_amount,
                            spreadsheet_id=spreadsheet_id,
                            row_number=next_row
                        )
                        
                        if 'error' in payment_data:
                            st.error(f"Payment Error: {payment_data['error']}")
                            return None
                        
                        # Display payment link
                        st.info("💳 Payment Required")
                        st.write(f"Amount: ${payment_amount:.2f}")
                        st.link_button("Complete Payment", payment_data['session_url'])
                        
                        # Store payment session with row information
                        if 'payment_sessions' not in st.session_state:
                            st.session_state.payment_sessions = {}
                            
                        # Create session data with all necessary information
                        session_data = {
                            'amount': payment_amount,
                            'form_data': form_data,
                            'spreadsheet_id': spreadsheet_id,
                            'sheet_name': sheet_name,
                            'row_number': next_row,
                            'username': st.session_state.get('username'),
                            'selected_sheet': st.session_state.get('selected_sheet'),
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        # Store in session state
                        st.session_state.payment_sessions[payment_data['session_id']] = session_data
                        logger.info("="*80)
                        logger.info("STORING PAYMENT SESSION")
                        logger.info(f"Session ID: {payment_data['session_id']}")
                        logger.info(f"Session Data: {session_data}")
                        logger.info("="*80)
                        return None
                except ValueError:
                    logger.error(f"Invalid payment amount: {form_data['Price']}")
                    st.error("Invalid payment amount specified")
                    return None
                
        except Exception as e:
            logger.error(f"Error in form submission: {str(e)}")
            st.error(f"Error submitting form: {str(e)}")
            return None

    @staticmethod
    def copy_volunteer_entry(spreadsheet_id: str, copy_service: CopyService, target_row: int) -> bool:
        """Copy volunteer entry to a specific row."""
        try:
            logger.info("=" * 60)
            logger.info("COPY OPERATION")
            logger.info("=" * 60)
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Target Row: {target_row}")
            
            source_range = "Volunteers!A2:Z2"
            logger.info(f"Source Range: {source_range}")

            success = copy_service.copy_entry(
                spreadsheet_id=spreadsheet_id,
                sheet_name="Volunteers",
                source_range=source_range,
                target_row=target_row
            )
            
            if success:
                success_msg = f"✅ Successfully copied to row {target_row} in Volunteers!"
                logger.info(success_msg)
                st.success(success_msg)
            else:
                error_msg = "Failed to copy entry"
                logger.error(error_msg)
                st.error(error_msg)
                
            return success
            
        except Exception as e:
            error_msg = f"Error during copy: {str(e)}"
            logger.error(error_msg)
            st.error(error_msg)
            return False

    @staticmethod
    def display_copy_test_button(spreadsheet_id: str, copy_service: CopyService) -> None:
        """Display test buttons and forms for various functionalities."""
        # Only show copy and test forms for admin users
        if not UIService.is_admin():
            return
            
        try:
            # 1. Copy to Selected Row Form
            st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin-bottom: 0.6rem;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">🔄 Copy Function</h3>
                </div>
            """, unsafe_allow_html=True)

            # Get available sheets for selection
            try:
                metadata = copy_service.sheets_client.get_spreadsheet_metadata(spreadsheet_id)
                sheet_names = [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]
                
                # Create sheet selector
                selected_sheet = st.selectbox(
                    "Select Sheet",
                    options=sheet_names,
                    index=sheet_names.index("Volunteers") if "Volunteers" in sheet_names else 0,
                    help="Select the sheet to copy from"
                )
            except Exception as e:
                logger.error(f"Error loading sheet names: {str(e)}")
                st.error("Failed to load sheet names")
                return
            
            # Row selection for the selected sheet
            target_row = st.number_input(
                "Target Row",
                min_value=1,
                value=6,
                step=1,
                help="Select the row number where you want to copy the data"
            )
            
            if st.button("Copy to Selected Row", type="primary", key="test_copy_button"):
                try:
                    # Display parameters on screen
                    st.info("Copy Operation Parameters:")
                    st.write({
                        "Spreadsheet ID": spreadsheet_id,
                        "Sheet Name": selected_sheet,
                        "Source Range": f"{selected_sheet}!A2:Z2",
                        "Target Row": target_row
                    })
                    
                    source_range = f"{selected_sheet}!A2:Z2"
                    st.write("About to execute copy_entry with these parameters")
                    
                    success = copy_service.copy_entry(
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=selected_sheet,
                        source_range=source_range,
                        target_row=target_row
                    )
                    
                    if success:
                        st.success(f"✅ Successfully copied to row {target_row} in {selected_sheet}!")
                    else:
                        st.error("Failed to copy entry")
                except Exception as e:
                    logger.error(f"Error during copy: {str(e)}")
                    st.error(f"Error: {str(e)}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 2. Cell Updates Form
            st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    padding: 0.5rem 0.8rem;
                    border-radius: 8px;
                    border-left: 5px solid #1E88E5;
                    margin: 1rem 0 0.6rem 0;
                ">
                    <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📝 Cell Updates</h3>
                </div>
            """, unsafe_allow_html=True)
            
            # Sheet name input
            sheet_name = st.text_input("Sheet Name", value="Volunteers", 
                                     help="Enter the name of the sheet to update",
                                     key="cell_updates_sheet_name")
            
            # Container for cell updates
            st.markdown("Enter row, column, and value for each cell to update")
            
            # Create 3 rows of inputs by default
            num_updates = 3
            cell_updates = []
            
            for i in range(num_updates):
                col1, col2, col3 = st.columns(3)
                with col1:
                    row = st.number_input(f"Row #{i+1}", 
                                        min_value=1, 
                                        value=4,
                                        key=f"row_{i}")
                with col2:
                    col = st.number_input(f"Column #{i+1}", 
                                        min_value=1,
                                        value=i+1,
                                        help="1=A, 2=B, etc",
                                        key=f"col_{i}")
                with col3:
                    val = st.text_input(f"Value #{i+1}",
                                      value=f"test{i+1}",
                                      key=f"val_{i}")
                cell_updates.extend([row, col, val])
            
            # Preserve form state in session state
            if 'cell_updates_active' not in st.session_state:
                st.session_state.cell_updates_active = False
                
            if st.button("Test Cell Updates", type="primary", key="test_cell_updates"):
                st.session_state.cell_updates_active = True
                try:
                    # Display parameters on screen
                    st.info("Cell Updates Operation Parameters:")
                    st.write({
                        "Spreadsheet ID": spreadsheet_id,
                        "Sheet Name": sheet_name,
                        "Cell Updates": cell_updates
                    })
                    
                    st.write("About to execute UpdateEntryCells with these parameters")
                    
                    from services.spreadsheet_service import SpreadsheetService
                    success = SpreadsheetService.UpdateEntryCells(
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=sheet_name,
                        cell_updates=cell_updates
                    )
                    if success:
                        st.success("✅ Cells updated successfully!")
                    else:
                        st.error("❌ Failed to update cells")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                finally:
                    # Reset state after operation
                    st.session_state.cell_updates_active = False
            
            st.markdown("<br>", unsafe_allow_html=True)
                
        except Exception as e:
            logger.error(f"Error displaying test buttons: {str(e)}")
            st.error("Failed to display test buttons")

    @staticmethod
    def display_sheet_data(df: pd.DataFrame, sheet_type: str = 'general'):
        """Display sheet data in appropriate format based on sheet type."""
        from services.table_service import TableService
        
        logger.info(f"UIService.display_sheet_data called with sheet_type: {sheet_type}")
        logger.info(f"DataFrame received - Shape: {df.shape}, Columns: {df.columns.tolist()}")
        logger.info(f"DataFrame dtypes: {df.dtypes.to_dict()}")
        
        # Validate DataFrame input
        if not isinstance(df, pd.DataFrame):
            logger.error(f"Invalid input type: {type(df)}")
            st.error("Invalid data format received")
            return
            
        # Add a visual indicator for results section
        st.markdown("""
            <div style="
                background-color: #f0f8ff;
                padding: 0.5rem 0.8rem;
                border-radius: 8px;
                border-left: 5px solid #1E88E5;
                margin-bottom: 0.6rem;
            ">
                <h3 style="margin: 0; color: #1E88E5; font-size: 1rem;">📊 Results</h3>
            </div>
        """, unsafe_allow_html=True)
        
        try:
            if sheet_type == 'outputs':
                # For OUTPUTS sheet, use static table with hidden headers
                TableService.display_static_table(df, hide_index=True, hide_header=True)
            else:
                # For general sheets, use interactive table
                TableService.display_interactive_table(df, enable_pagination=False, allow_export=True)
        except Exception as e:
            logger.error(f"Error displaying dataframe: {str(e)}")
            st.error("Error displaying data. Please check the data format.")
            # Fallback to basic display
            st.dataframe(df)  # Using st.dataframe instead of st.write for better DataFrame handling