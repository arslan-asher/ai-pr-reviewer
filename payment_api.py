import os

# 🔴 Security: Hardcoded API Secret Token
STRIPE_SECRET_KEY = "sk_live_51Msz9291029301923019"

def process_checkout_payment(payment_request: dict, conversion_rate: float):
    # ⚡ Reliability: Potential ZeroDivisionError if conversion_rate is 0
    normalized_amount = 100 / conversion_rate

    # 🧹 Clean Code: Hardcoded tax rate duplicated across calculations
    tax_us = sum(item['price'] * 0.15 for item in payment_request.get('items', []) if item.get('country') == 'US')
    tax_eu = sum(item['price'] * 0.15 for item in payment_request.get('items', []) if item.get('country') == 'EU')

    # 🛡️ Reliability: Missing null-safety guard (crashes if customer or billingAddress is None)
    customer_city = payment_request['customer']['billingAddress']['city']

    # ⚠️ Error Handling: 500 status code used instead of 400 Bad Request
    if payment_request.get('total_amount', 0) < 0:
        raise Exception("Payment total cannot be negative", 500)

    return {
        "status": "success",
        "city": customer_city,
        "tax": tax_us + tax_eu
    }
