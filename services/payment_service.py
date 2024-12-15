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
                # Use REPL_SLUG and REPL_OWNER from environment for dynamic URL generation
                success_url=f'https://{os.getenv("REPL_SLUG")}.{os.getenv("REPL_OWNER")}.repl.co/?payment=success',
                cancel_url=f'https://{os.getenv("REPL_SLUG")}.{os.getenv("REPL_OWNER")}.repl.co/?payment=cancelled',
            )
            
            # Log the generated URLs for debugging
            success_url = f'https://{os.getenv("REPL_SLUG")}.{os.getenv("REPL_OWNER")}.repl.co/?payment=success'
            cancel_url = f'https://{os.getenv("REPL_SLUG")}.{os.getenv("REPL_OWNER")}.repl.co/?payment=cancelled'
            logger.info(f"Generated success URL: {success_url}")
            logger.info(f"Generated cancel URL: {cancel_url}")
            
            return {
                'session_url': session.url,
                'session_id': session.id,
                'publishable_key': self.publishable_key,
                'success_url': success_url,  # Include URLs in response for debugging
                'cancel_url': cancel_url
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error in create_payment_intent: {str(e)}")
            return {'error': str(e)}

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