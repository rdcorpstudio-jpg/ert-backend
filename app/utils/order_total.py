def calculate_order_total(items):
    total = 0
    for item in items:
        total += float(item.unit_price) - float(item.discount)
    return total
