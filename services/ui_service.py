"""Service for handling UI components and displays."""
import logging
import os
import json
from datetime import datetime, date
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
            # Entry point logging with detailed information
            logger.info("="*80)
            logger.info("PAYMENT VERIFICATION STARTED")
            logger.info("="*80)
            logger.info(f"Processing session ID: {session_id}")
            logger.info(f"Query parameters: {json.dumps(dict(st.query_params), default=str)}")
            logger.info(f"Session state keys: {json.dumps(list(st.session_state.keys()), default=str)}")
            logger.info("="*80)

            # Initialize payment service and verify payment status
            logger.info("="*80)
            logger.info("INITIALIZING PAYMENT SERVICE")
            logger.info("="*80)
            
            from services.payment_service import PaymentService
            payment_service = PaymentService()

            # Get payment status from Stripe
            logger.info("Retrieving payment status from Stripe...")
            payment_status = payment_service.get_payment_status(session_id)
            
            if not payment_status:
                logger.error("Failed to retrieve payment status")
                return False
                
            # Log complete payment status for debugging
            logger.info("="*80)
            logger.info("PAYMENT STATUS DETAILS")
            logger.info(f"Full payment status: {json.dumps(payment_status, default=str, indent=2)}")
            logger.info("="*80)

            logger.info("="*80)
            logger.info("PAYMENT STATUS")
            logger.info(f"Status: {payment_status.get('status')}")
            logger.info("="*80)

            # Verify payment was successful
            if payment_status.get('status') != 'succeeded':
                logger.error(f"Payment not successful. Status: {payment_status.get('status')}")
                return False

            # Extract metadata for sheet update
            metadata = payment_status.get('metadata', {})
            spreadsheet_id = metadata.get('spreadsheet_id')
            row_number = metadata.get('row_number')

            # Log metadata details
            logger.info("="*80)
            logger.info("STRIPE CALLBACK METADATA")
            logger.info(f"Raw metadata: {json.dumps(metadata, default=str, indent=2)}")
            logger.info(f"Spreadsheet ID: {spreadsheet_id}")
            logger.info(f"Row Number: {row_number}")
            logger.info("="*80)

            if not spreadsheet_id or not row_number:
                logger.error("Missing required metadata")
                return False

            try:
                row_number = int(row_number)
            except ValueError:
                logger.error(f"Invalid row number format: {row_number}")
                return False

            # Initialize SpreadsheetService for sheet update
            from services.spreadsheet_service import SpreadsheetService

            # Verify sheet exists and is accessible
            sheet_metadata = sheets_client.get_spreadsheet_metadata(spreadsheet_id)
            if not sheet_metadata:
                logger.error("Failed to retrieve sheet metadata")
                return False

            available_sheets = [sheet['properties']['title'] for sheet in sheet_metadata.get('sheets', [])]
            logger.info(f"Available sheets: {available_sheets}")

            if 'Sponsors' not in available_sheets:
                logger.error("Sponsors sheet not found in spreadsheet")
                return False

            # Verify sheet access and row validity
            df = sheets_client.read_spreadsheet(spreadsheet_id, 'Sponsors!A:H')
            if df is None:
                logger.error("Failed to read Sponsors sheet")
                return False

            logger.info(f"Sheet read successfully - Total rows: {len(df)}")
            logger.info(f"Attempting to update row {row_number}")
            
            # Allow any row within reasonable range (e.g., first 1000 rows)
            if row_number <= 0 or row_number > 1000:
                logger.error(f"Row number {row_number} is out of valid range (1-1000)")
                return False
                
            logger.info(f"Row {row_number} is within valid range, proceeding with update")

            # Read headers to detect Paid column position
            logger.info("=" * 80)
            logger.info("DETECTING PAID COLUMN")
            logger.info("=" * 80)

            # Read headers to detect Paid column position
            header_range = 'Sponsors!A1:Z1'
            df_headers = sheets_client.read_spreadsheet(spreadsheet_id, header_range)
            
            logger.info("=" * 80)
            logger.info("HEADER DETECTION")
            logger.info(f"DataFrame headers: {df_headers}")
            
            try:
                if df_headers is None:
                    logger.error("Failed to read header data")
                    return False
                
                # Get the column names directly from DataFrame
                headers = list(df_headers.columns)
                logger.info(f"Column headers: {headers}")
                
                # Examine each header value
                logger.info("Examining headers:")
                for i, header in enumerate(headers):
                    header_str = str(header).strip()
                    logger.info(f"Column {chr(65+i)}: '{header_str}'")
                
                # Search for 'Paid' in the headers with detailed logging
                paid_column_name = 'Paid'
                paid_column_index = None
                
                # Examine each header for exact match
                for i, header in enumerate(headers):
                    header_str = str(header).strip()
                    logger.info(f"Checking column {chr(65+i)}: '{header_str}' against '{paid_column_name}'")
                    if header_str == paid_column_name:
                        paid_column_index = i + 1  # Add 1 for 1-based spreadsheet columns
                        logger.info(f"Found exact match for '{paid_column_name}' at column {chr(64+paid_column_index)}")
                        break
                
                if paid_column_index is None:
                    logger.error(f"Could not find exact match for '{paid_column_name}' column in headers: {headers}")
                    return False
                    
                logger.info(f"Will update column {chr(64+paid_column_index)} with payment status")
            except Exception as e:
                logger.error(f"Error finding Paid column: {str(e)}")
                return False

            payment_status = f"PAID_STRIPE_{session_id}"
            
            # Verify current value before update
            current_data = sheets_client.read_spreadsheet(spreadsheet_id, f'Sponsors!{chr(64 + paid_column_index)}{row_number}')
            if current_data is not None and not current_data.empty:
                logger.info(f"Current value in cell {chr(64 + paid_column_index)}{row_number}: {current_data.iloc[0, 0] if not current_data.empty else 'Empty'}")
            
            cell_updates = [row_number, paid_column_index, payment_status]
            
            # Log detailed update information
            logger.info("="*80)
            logger.info("PAYMENT STATUS UPDATE DETAILS")
            logger.info(f"Target Cell: {chr(64 + paid_column_index)}{row_number}")
            logger.info(f"Column Letter: {chr(64 + paid_column_index)} (I)")
            logger.info(f"Column Index: {paid_column_index}")
            logger.info(f"Row Number: {row_number}")
            logger.info(f"New Value: {payment_status}")
            logger.info("="*80)

            # Verify current value before update
            current_data = sheets_client.read_spreadsheet(spreadsheet_id, f'Sponsors!{chr(64 + paid_column_index)}{row_number}')
            if current_data is not None and not current_data.empty:
                logger.info(f"Current value in cell: {current_data.iloc[0, 0] if not current_data.empty else 'Empty'}")

            # Execute the update
            try:
                update_success = SpreadsheetService.UpdateEntryCells(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name='Sponsors',
                    cell_updates=cell_updates
                )
                logger.info(f"Sheet update result: {update_success}")
            except Exception as update_error:
                logger.error(f"Error during sheet update: {str(update_error)}")
                raise

            if update_success:
                logger.info("Successfully updated payment status in sheet")
                st.success("✅ Payment verified and entry updated successfully!")
                return True
            else:
                logger.error("Failed to update sheet")
                st.error("Failed to update payment status in sheet")
                return False

        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
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
        try:
            # Convert form data to serializable format and store it
            serializable_form_data = {}
            for key, value in form_data.items():
                if isinstance(value, (datetime, date)):
                    serializable_form_data[key] = value.isoformat()
                else:
                    serializable_form_data[key] = str(value)

            # Convert form data to strings for spreadsheet update
            stringified_form_data = {k: str(v) for k, v in serializable_form_data.items()}

            logger.info("=" * 80)
            logger.info("FORM SUBMISSION HANDLER")
            logger.info("=" * 80)
            logger.info(f"Processing submission for sheet: {sheet_name}")
            logger.info(f"Form data received: {json.dumps(stringified_form_data, indent=2)}")

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

            # Use stringified form data for cell updates
            for field_name, value in stringified_form_data.items():
                field_info = next((f for f in form_fields if f['name'] == field_name), None)
                if field_info:
                    column_index = field_info['column_index'] + 1
                    # Ensure value is a string
                    cell_updates.extend([next_row, column_index, value])

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

                        # Save current application state to environment for Stripe metadata
                        os.environ['CURRENT_USERNAME'] = st.session_state.get('username', '')
                        os.environ['SELECTED_SHEET'] = st.session_state.get('selected_sheet', '')
                        os.environ['CURRENT_SHEET_TAB'] = sheet_name

                        # Display payment information and redirect button
                        st.info("💳 Payment Required")
                        st.write(f"Amount: ${payment_amount:.2f}")
                        
                        # Use JavaScript to redirect in current window
                        js_code = f"""
                        <script>
                            function redirectToPayment() {{
                                window.location.href = "{payment_data['session_url']}";
                            }}
                        </script>
                        <button 
                            onclick="redirectToPayment()" 
                            style="
                                background-color: #4CAF50; 
                                color: white; 
                                padding: 12px 20px; 
                                border: none; 
                                border-radius: 4px; 
                                cursor: pointer;
                            "
                        >
                            Complete Payment
                        </button>
                        """
                        st.markdown(js_code, unsafe_allow_html=True)
                        
                        # Log the payment flow initiation
                        logger.info("="*80)
                        logger.info("PAYMENT FLOW INITIATED")
                        logger.info(f"Username: {os.environ.get('CURRENT_USERNAME')}")
                        logger.info(f"Selected Sheet: {os.environ.get('SELECTED_SHEET')}")
                        logger.info(f"Current Tab: {os.environ.get('CURRENT_SHEET_TAB')}")
                        logger.info(f"Amount: ${payment_amount:.2f}")
                        logger.info(f"Session URL: {payment_data['session_url']}")
                        logger.info("="*80)
                        # Store metadata for logging
                        metadata_log = {
                            'session_id': payment_data['session_id'],
                            'username': os.environ.get('CURRENT_USERNAME', ''),
                            'selected_sheet': os.environ.get('SELECTED_SHEET', ''),
                            'current_tab': os.environ.get('CURRENT_SHEET_TAB', ''),
                            'amount': f"${payment_amount:.2f}",
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        logger.info("="*80)
                        logger.info("STORING PAYMENT SESSION")
                        logger.info(f"Session ID: {payment_data['session_id']}")
                        logger.info(f"Session Data: {json.dumps(metadata_log, indent=2)}")
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