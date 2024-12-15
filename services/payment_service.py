import os
import logging
import stripe
from typing import Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        """Initialize the payment service with Stripe API keys."""
        try:
            self.secret_key = os.getenv('STRIPE_SECRET_KEY')
            self.publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
            
            if not self.secret_key or not self.publishable_key:
                logger.error("Missing required Stripe API keys")
                raise ValueError("Missing required Stripe API keys")
            
            if not (self.secret_key.startswith('sk_') and self.publishable_key.startswith('pk_')):
                logger.error("Invalid Stripe API key format")
                raise ValueError("Invalid Stripe API key format. Secret key should start with 'sk_' and publishable key with 'pk_'")
                
            # Configure Stripe client
            stripe.api_key = self.secret_key
            
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
            
            # Get the Replit slug for the application
            replit_slug = os.getenv('REPLIT_SLUG', 'sheetsyncwebalwayson')
            
            # Use correct Replit domain structure (without owner)
            base_url = f"https://{replit_slug}.repl.co"
            logger.info(f"Using Replit URL for callbacks: {base_url}")
            
            # Validate URL construction
            if not all(c.isalnum() or c in '.-' for c in replit_slug):
                error_msg = "Invalid Replit slug"
                logger.error(f"{error_msg}: slug={replit_slug}")
                raise ValueError(error_msg)
            
            logger.info(f"Base URL for Stripe redirects: {base_url}")
            
            # Create success and cancel URLs with query parameters
            success_url = f"{base_url}/?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{base_url}/?payment=cancelled"
            
            # Log the generated URLs
            logger.info(f"Success URL template: {success_url}")
            logger.info(f"Cancel URL: {cancel_url}")
            
            # Create Stripe Checkout session
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

    def get_payment_status(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Get the status of a payment intent
        
        Args:
            payment_intent_id: The ID of the payment intent to check
            
        Returns:
            Dict containing payment status and details
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return {
                'status': intent.status,
                'amount': intent.amount / 100,  # Convert cents to dollars
                'currency': intent.currency
            }
        except stripe.error.StripeError as e:
            return {'error': str(e)}
