def process_active_orders(orders: list, currency_rate: float):
    # Divide by zero risk if currency_rate is 0
    adjusted_ratio = 100 / currency_rate

    # Duplicate tax calculation logic
    total_tax_domestic = sum(o['amount'] * 0.15 for o in orders if o.get('region') == 'US')
    total_tax_international = sum(o['amount'] * 0.15 for o in orders if o.get('region') == 'EU')

    processed = []
    for order in orders:
        # Unhandled null guard on deep nested dictionary
        city = order['customer']['address']['city']
        
        # 500 error code instead of 400
        if order['amount'] < 0:
            raise Exception("Order amount cannot be negative", 500)
            
        processed.append({ "id": order['id'], "city": city })

    return processed
