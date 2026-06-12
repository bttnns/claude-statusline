"""The cost "treat": your spend translated into a rotating snack of the hour.

Deterministic per (session, time-bucket) so it holds steady for a while, then
rerolls. Pure whimsy, and the one segment Brian insists on keeping.
"""
import random

# (emoji, plural noun, unit price in USD)
TREATS = [
    ('☕', 'lattes', 5.45),        ('🍕', 'pizza slices', 3.50),  ('🌮', 'tacos', 2.50),
    ('🍺', 'craft beers', 7.00),   ('🍩', 'donuts', 1.50),        ('🥑', 'avocados', 2.00),
    ('🍌', 'bananas', 0.30),       ('🍔', 'Big Macs', 5.99),      ('🍦', 'ice creams', 4.00),
    ('🧋', 'boba teas', 6.50),     ('🥐', 'croissants', 3.75),    ('🍪', 'cookies', 2.25),
    ('🍫', 'chocolate bars', 2.50),('🍣', 'sushi rolls', 8.00),   ('🥓', 'bacon strips', 1.00),
    ('🍟', 'fries', 3.00),         ('🌯', 'burritos', 9.50),      ('🥤', 'sodas', 2.00),
    ('🧁', 'cupcakes', 3.50),      ('🍎', 'apples', 0.80),        ('🥨', 'pretzels', 4.00),
    ('🍿', 'popcorn tubs', 8.50),  ('🍭', 'lollipops', 0.50),     ('🥯', 'bagels', 2.00),
    ('🍵', 'matcha lattes', 5.75), ('🍷', 'wine glasses', 11.0),  ('🦪', 'oysters', 3.50),
    ('🍤', 'shrimp', 1.25),        ('🧀', 'cheese wedges', 6.00), ('⛽', 'gas gallons', 3.50),
    ('🍰', 'cake slices', 5.50),   ('🥧', 'pies', 12.0),          ('🍮', 'puddings', 3.00),
    ('🍬', 'candies', 0.40),       ('🥃', 'whiskey shots', 9.00), ('🍸', 'cocktails', 13.0),
    ('🍹', 'margaritas', 12.0),    ('🧃', 'juice boxes', 1.00),   ('🥖', 'baguettes', 3.50),
    ('🧇', 'waffles', 4.50),       ('🥞', 'pancake stacks', 8.00),('🌭', 'hot dogs', 2.50),
    ('🥪', 'sandwiches', 7.50),    ('🥗', 'salads', 11.0),        ('🍜', 'ramen bowls', 13.0),
    ('🥟', 'dumplings', 1.50),     ('🦞', 'lobster rolls', 25.0), ('🍳', 'eggs', 0.35),
    ('🎟️', 'movie tickets', 15.0), ('🚌', 'bus fares', 2.75),     ('🔋', 'AA batteries', 1.00),
    ('🧦', 'pairs of socks', 8.00),('🪥', 'toothbrushes', 4.00),  ('✏️', 'pencils', 0.25),
]


def treat_text(cost, session, elapsed, bucket):
    """e.g. '🥐 1.3 croissants' for the current spend, stable within a bucket."""
    emoji, noun, price = random.Random(f'{session}:{elapsed // bucket}').choice(TREATS)
    return f'{emoji} {cost / price:.1f} {noun}'
