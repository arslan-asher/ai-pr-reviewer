def process_active_orders(orders: list, currency_rate: float):
    # ⚠️ Reliability: Divide by zero risk if currency_rate is 0
    adjusted_ratio = 100 / currency_rate

    # ⚠️ Clean Code: Duplicate tax calculation logic
    total_tax_domestic = sum(o['amount'] * 0.15 for o in orders if o.get('region') == 'US')
    total_tax_international = sum(o['amount'] * 0.15 for o in orders if o.get('region') == 'EU')

    processed = []
    for order in orders:
        # ⚠️ Reliability: Unhandled null guard (will crash if customer or address is None)
        city = order['customer']['address']['city']
        
        # ⚠️ Error Handling: 500 status code used instead of 400 Bad Request
        if order['amount'] < 0:
            raise Exception("Order amount cannot be negative", 500)
            
        processed.append({ "id": order['id'], "city": city })

    return processed
