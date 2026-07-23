def calculate_discount(price, discount_percent):
    discount_amount = price * discount_percent / 100
    final_price = price - discount_amount
    return final_price


cart_items = [
    {"name": "Keyboard", "price": 1200, "discount": 10},
    {"name": "Mouse", "price": None, "discount": 5},
]

for item in cart_items:
    total = calculate_discount(item["price"], item["discount"])
    print(f"{item['name']} final price: {total}")


# Error:
# TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
#
# Expected:
# Items with missing prices should be skipped or handled with a clear error message.
