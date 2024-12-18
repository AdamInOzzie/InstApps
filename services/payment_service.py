import os
import logging
import stripe
import streamlit as st
from typing import Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        """Initialize the payment service with Stripe API keys."""
        try:
            # Get API keys with detailed logging
            self.secret_key = os.getenv('STRIPE_SECRET_KEY')
            self.publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
            
            logger.info("Checking Stripe API keys...")
            
            # Check each key individually with detailed logging
            missing_keys = []
            invalid_keys = []
            
            # Check secret key
            if not self.secret_key:
                missing_keys.append('STRIPE_SECRET_KEY')
                logger.error("STRIPE_SECRET_KEY is completely missing from environment variables")
            elif not isinstance(self.secret_key, str):
                invalid_keys.append('STRIPE_SECRET_KEY (invalid type)')
                logger.error(f"STRIPE_SECRET_KEY has invalid type: {type(self.secret_key)}")
            else:
                logger.info("STRIPE_SECRET_KEY is present in environment")
                
            # Check publishable key
            if not self.publishable_key:
                missing_keys.append('STRIPE_PUBLISHABLE_KEY')
                logger.error("STRIPE_PUBLISHABLE_KEY is completely missing from environment variables")
            elif not isinstance(self.publishable_key, str):
                invalid_keys.append('STRIPE_PUBLISHABLE_KEY (invalid type)')
                logger.error(f"STRIPE_PUBLISHABLE_KEY has invalid type: {type(self.publishable_key)}")
            else:
                logger.info("STRIPE_PUBLISHABLE_KEY is present in environment")
            
            # Handle missing or invalid keys
            if missing_keys or invalid_keys:
                error_details = []
                if missing_keys:
                    error_details.append(f"Missing keys: {', '.join(missing_keys)}")
                if invalid_keys:
                    error_details.append(f"Invalid keys: {', '.join(invalid_keys)}")
                    
                error_msg = "Stripe API key configuration error: " + "; ".join(error_details)
                logger.error(error_msg)
                logger.error("Please ensure all required keys are properly set in the deployment environment")
                logger.error("Keys should be exported as environment variables before starting the application")
                raise ValueError(error_msg)
            
            # Validate key formats
            if not self.secret_key.startswith('sk_'):
                error_msg = "Invalid secret key format. Must start with 'sk_'"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            if not self.publishable_key.startswith('pk_'):
                error_msg = "Invalid publishable key format. Must start with 'pk_'"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            # Configure Stripe client
            logger.info("Configuring Stripe client...")
            stripe.api_key = self.secret_key
            logger.info("Stripe client configured successfully")
            
            # Log initialization status (without exposing keys)
            logger.info("PaymentService initialized with Stripe keys")
            logger.info(f"Secret key prefix: {self.secret_key[:7]}...")
            logger.info(f"Publishable key prefix: {self.publishable_key[:7]}...")
            
        except Exception as e:
            logger.error(f"Failed to initialize PaymentService: {str(e)}")
            raise

    def create_payment_intent(self, amount: float, currency: str = 'usd') -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for the specified amount
        
        Args:
            amount: Amount in dollars (will be converted to cents)
            currency: Currency code (default: 'usd')
            
        Returns:
            Dict containing session url and other payment details
        """
        try:
            # Convert dollars to cents for Stripe
            amount_cents = int(amount * 100)
            
            # Get the application URL from environment or fallback to a local URL
            base_url = os.getenv('APP_URL', 'http://localhost:5000')
            
            # Remove trailing slash if present
            base_url = base_url.rstrip('/')
            
            logger.info(f"Using base URL for redirects: {base_url}")
            logger.info(f"Using Replit URL for callbacks: {base_url}")
            
            # Log the base URL being used
            logger.info(f"Base URL for Stripe redirects: {base_url}")
            
            # Create success and cancel URLs with query parameters
            success_url = f"{base_url}/?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{base_url}/?payment=cancelled"
            
            # Log the generated URLs
            logger.info(f"Success URL template: {success_url}")
            logger.info(f"Cancel URL: {cancel_url}")
            
            # Initialize payment_sessions if not exists
            if 'payment_sessions' not in st.session_state:
                st.session_state.payment_sessions = {}
                
            # Create Stripe Checkout session
            session_data = {}
            
            # Get current session data if it exists
            current_session_id = st.session_state.get('current_session_id', '')
            session_data = st.session_state.payment_sessions.get(current_session_id, {})

            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': currency,
                        'unit_amount': amount_cents,
                        'product_data': {
                            'name': 'Payment',
                            'description': 'Form submission payment',
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'row_number': str(session_data.get('row_number', '')),
                    'sheet_name': session_data.get('sheet_name', ''),
                    'spreadsheet_id': session_data.get('spreadsheet_id', ''),
                    'amount': str(amount)
                }
            )
            
            # Log the URLs for debugging
            logger.info(f"Generated success URL: {success_url}")
            logger.info(f"Generated cancel URL: {cancel_url}")
            
            return {
                'session_url': session.url,
                'session_id': session.id,
                'publishable_key': self.publishable_key,
                'success_url': success_url,
                'cancel_url': cancel_url
            }
        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Stripe error type: {type(e).__name__}")
            logger.error(f"Stripe error details: {e.user_message if hasattr(e, 'user_message') else str(e)}")
            return {
                'error': error_msg,
                'error_type': 'stripe_error',
                'details': e.user_message if hasattr(e, 'user_message') else str(e)
            }
        except Exception as e:
            error_msg = f"Payment processing error: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full error details: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            return {
                'error': error_msg,
                'error_type': 'system_error',
                'details': str(e)
            }

    def get_payment_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get the status of a checkout session
        
        Args:
            session_id: The ID of the checkout session to check
            
        Returns:
            Dict containing payment status and details
        """
        try:
            logger.info(f"Retrieving payment status for session: {session_id}")
            session = stripe.checkout.Session.retrieve(session_id)
            payment_status = session.payment_status
            logger.info(f"Payment status retrieved: {payment_status}")
            logger.info(f"Full session data: {session}")
            
            return {
                'status': 'succeeded' if payment_status == 'paid' else payment_status,
                'amount': session.amount_total / 100,  # Convert cents to dollars
                'currency': session.currency,
                'payment_intent': session.payment_intent,
                'metadata': session.metadata
            }
        except stripe.error.StripeError as e:
            return {'error': str(e)}
