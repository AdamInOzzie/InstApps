import os
import stripe
from typing import Dict, Any

class PaymentService:
    def __init__(self):
        """Initialize the payment service with Stripe API keys."""
        self.secret_key = os.getenv('STRIPE_SECRET_KEY')
        self.publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
        
        if not self.secret_key or not self.publishable_key:
            raise ValueError("Missing required Stripe API keys")
            
        # Configure Stripe client
        stripe.api_key = self.secret_key
        
        # Log initialization status (without exposing keys)
        logging.info("PaymentService initialized with Stripe keys")
        logging.info(f"Secret key prefix: {self.secret_key[:7]}...")
        logging.info(f"Publishable key prefix: {self.publishable_key[:7]}...")

    def create_payment_intent(self, amount: float, currency: str = 'usd') -> Dict[str, Any]:
        """
        Create a payment intent for the specified amount
        
        Args:
            amount: Amount in dollars (will be converted to cents)
            currency: Currency code (default: 'usd')
            
        Returns:
            Dict containing client_secret and other payment details
        """
        try:
            # Convert dollars to cents for Stripe
            amount_cents = int(amount * 100)
            
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency
            )
            
            return {
                'client_secret': intent.client_secret,
                'publishable_key': self.publishable_key
            }
        except stripe.error.StripeError as e:
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
