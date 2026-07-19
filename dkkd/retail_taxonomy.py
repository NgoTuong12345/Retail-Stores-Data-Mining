"""Global retail classification: one namespace, covering every DKKD-scraped
brand via a VN folder-subsector crosswalk (classify_by_folder), plus a
lower-level classify_by_taxonomy_node() entry point keyed on the same node
vocabulary, for a brand's derived deepest store-format category when one is
known independent of its folder placement.

See docs/superpowers/specs/2026-07-09-global-retail-classification-design.md
for the full design (offline-subtree restriction rule, node/subsector maps).
"""

_NONE_RESULT = {
    'gics_sector': None, 'retail_subsector': None,
    'retail_format': None, 'channel_type': None,
}

# Taxonomy node name -> (gics_sector, retail_subsector). Covers exactly the
# 14 L3 nodes under the offline store-format subtree (Grocery Retailers,
# Non-Grocery Retailers) — channel branches (Direct Selling, Vending, Retail
# E-Commerce by Type) are deliberately absent so classify_by_taxonomy_node()
# rejects them instead of inventing a retail format.
L3_TO_CLASS = {
    'Convenience Retailers': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Discounters': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Hypermarkets': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Small Local Grocers': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Supermarkets': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Warehouse Clubs': ('Consumer Staples', 'Food & Beverage / Grocery Retail'),
    'Food/Drink/Tobacco Specialists': ('Consumer Staples', 'Food & Beverage Retail — Specialist'),
    # Health and Beauty -> Staples is a judgment default (premium beauty
    # could be Discretionary); confirmed with user during design review.
    'Health and Beauty Specialists': ('Consumer Staples', 'Health & Personal Care Retail'),
    'Apparel and Footwear Specialists': ('Consumer Discretionary', 'Apparel & Footwear Retail'),
    'Appliances and Electronics Specialists': ('Consumer Discretionary', 'Electronics & Appliance Retail'),
    'Leisure and Personal Goods Specialists': ('Consumer Discretionary', 'Leisure & Personal Goods Retail'),
    'Home Products Specialists': ('Consumer Discretionary', 'Home & Garden Retail'),
    'General Merchandise Stores': ('Consumer Discretionary', 'General Merchandise Retail'),
    'Other Non-Grocery Retailers': ('Consumer Discretionary', 'Other Specialty Retail'),
}

# VN brands/<industry>/<subsector>/ folder slug -> (node_name, l3_name) in the
# same namespace classify_by_taxonomy_node() uses. node_name is the more
# specific leaf where the tree has one (e.g. Pharmacies under Health and
# Beauty Specialists); otherwise it equals l3_name.
_FOLDER_TO_NODE = {
    'convenience_stores': ('Convenience Stores', 'Convenience Retailers'),
    'mini_supermarket': ('Small Local Grocers', 'Small Local Grocers'),
    'supermarket': ('Supermarkets', 'Supermarkets'),
    'hyper_supermarket': ('Hypermarkets', 'Hypermarkets'),
    'bakery_stores': ('Food/Drink/Tobacco Specialists', 'Food/Drink/Tobacco Specialists'),
    'drug_stores': ('Pharmacies', 'Health and Beauty Specialists'),
    'cosmetic_stores': ('Beauty Specialists', 'Health and Beauty Specialists'),
    'optical_stores': ('Optical Goods Stores', 'Health and Beauty Specialists'),
    'gold_chains': ('Jewellery and Watch Specialists', 'Leisure and Personal Goods Specialists'),
    'ict_stores': ('Appliances and Electronics Specialists', 'Appliances and Electronics Specialists'),
    'electronic_stores': ('Appliances and Electronics Specialists', 'Appliances and Electronics Specialists'),
    'fashion_apparel': ('Apparel and Footwear Specialists', 'Apparel and Footwear Specialists'),
    'sports_stores': ('Sports Goods', 'Leisure and Personal Goods Specialists'),
    'kids_baby_stores': ('Other Non-Grocery Retailers', 'Other Non-Grocery Retailers'),
    'bookstores': ('Leisure and Personal Goods Specialists', 'Leisure and Personal Goods Specialists'),
    'mini_stores': ('Variety Stores', 'General Merchandise Stores'),
}

# Foodservice subsectors — outside the retail-only taxonomy tree entirely,
# so they never route through classify_by_taxonomy_node(); labeled directly.
_FOODSERVICE_FORMAT = {
    'coffee_chains': 'Specialist Coffee Shop',
    'milktea': 'Bubble Tea / Café',
    'fast_food_chains': 'Fast Food',
    'restaurant_chains': 'Full-Service Restaurant',
    'food_chain': 'Fast Food / Quick Service',
}

# Non-retail service subsectors — also absent from the retail tree.
_SERVICES_CLASS = {
    'shopping_malls': ('Consumer Discretionary', 'General Merchandise Retail', 'Shopping Mall / Mixed Retailer'),
    'movie_theatres': ('Consumer Discretionary', 'Consumer Services', 'Cinema'),
    'fitness_stores': ('Consumer Discretionary', 'Consumer Services', 'Fitness Centre'),
}


def classify_by_taxonomy_node(node_name: str, l3_name: str) -> dict:
    """Classify from a taxonomy node. `node_name` is the brand's derived
    deepest offline category (may equal `l3_name` if that L3 node has no
    deeper children); `l3_name` is its L3 ancestor, used to look up the
    sector/subsector rollup. Returns all-None for anything outside the
    offline Grocery/Non-Grocery store-format subtree (channel branches,
    unrecognized nodes) rather than guessing.
    """
    cls = L3_TO_CLASS.get(l3_name)
    if cls is None:
        return dict(_NONE_RESULT)
    gics_sector, retail_subsector = cls
    return {
        'gics_sector': gics_sector, 'retail_subsector': retail_subsector,
        'retail_format': node_name, 'channel_type': 'Retail',
    }


def classify_by_folder(subsector: str) -> dict:
    """Classify a VN brand from its brands/<industry>/<subsector>/ folder
    slug, crosswalked onto the same taxonomy classify_by_taxonomy_node()
    uses. Unknown subsector -> all-None (fail-open, not a guess).
    """
    if subsector in _FOODSERVICE_FORMAT:
        return {
            'gics_sector': 'Consumer Discretionary', 'retail_subsector': 'Consumer Foodservice',
            'retail_format': _FOODSERVICE_FORMAT[subsector], 'channel_type': 'Foodservice',
        }
    if subsector in _SERVICES_CLASS:
        gics_sector, retail_subsector, retail_format = _SERVICES_CLASS[subsector]
        return {
            'gics_sector': gics_sector, 'retail_subsector': retail_subsector,
            'retail_format': retail_format, 'channel_type': 'Services',
        }
    node = _FOLDER_TO_NODE.get(subsector)
    if node is None:
        return dict(_NONE_RESULT)
    node_name, l3_name = node
    return classify_by_taxonomy_node(node_name, l3_name)


def demo():
    live_subsectors = [
        'bakery_stores', 'coffee_chains', 'convenience_stores', 'fast_food_chains',
        'food_chain', 'hyper_supermarket', 'milktea', 'mini_supermarket',
        'restaurant_chains', 'supermarket', 'ict_stores', 'bookstores',
        'cosmetic_stores', 'electronic_stores', 'fashion_apparel', 'fitness_stores',
        'gold_chains', 'mini_stores', 'shopping_malls', 'kids_baby_stores',
        'movie_theatres', 'optical_stores', 'drug_stores', 'sports_stores',
    ]
    for s in live_subsectors:
        result = classify_by_folder(s)
        assert result['retail_format'] is not None, f"unclassified folder subsector: {s}"
    assert classify_by_taxonomy_node('Convenience Stores', 'Convenience Retailers')['gics_sector'] == 'Consumer Staples'
    assert classify_by_taxonomy_node('Marketplace', 'Marketplace') == dict(_NONE_RESULT)
    print(f"OK: {len(live_subsectors)} live folder subsectors all classify cleanly")


if __name__ == '__main__':
    demo()
