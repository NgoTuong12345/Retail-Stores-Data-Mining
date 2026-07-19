"""Tests for dkkd/retail_taxonomy.py — the single global classification map:
taxonomy node -> (gics_sector, retail_subsector, retail_format, channel_type),
plus the VN folder-subsector crosswalk onto the same nodes.
"""
from dkkd import retail_taxonomy as rt

# The 24 subsector slugs actually on disk under brands/ (see CLAUDE.md /
# brands/ directory tree) — every one must resolve to a non-None result.
LIVE_FOLDER_SUBSECTORS = [
    'bakery_stores', 'coffee_chains', 'convenience_stores', 'fast_food_chains',
    'food_chain', 'hyper_supermarket', 'milktea', 'mini_supermarket',
    'restaurant_chains', 'supermarket',
    'ict_stores', 'bookstores', 'cosmetic_stores', 'electronic_stores',
    'fashion_apparel', 'fitness_stores', 'gold_chains', 'mini_stores',
    'shopping_malls', 'kids_baby_stores', 'movie_theatres', 'optical_stores',
    'drug_stores', 'sports_stores',
]

# Every taxonomy L3 node under the offline store-format subtree (Grocery
# Retailers / Non-Grocery Retailers).
OFFLINE_L3_NODES = [
    'Convenience Retailers', 'Discounters', 'Hypermarkets', 'Small Local Grocers',
    'Supermarkets', 'Warehouse Clubs', 'Food/Drink/Tobacco Specialists',
    'Health and Beauty Specialists', 'Apparel and Footwear Specialists',
    'Appliances and Electronics Specialists', 'Leisure and Personal Goods Specialists',
    'Home Products Specialists', 'General Merchandise Stores', 'Other Non-Grocery Retailers',
]

# Channel branches (Direct Selling / Vending / Retail E-Commerce by Type) —
# NOT store formats; classify_by_taxonomy_node must reject these, not treat
# them as retail formats.
CHANNEL_L3_NODES = [
    'Fashion Direct Selling and E-Commerce', 'Foods Vending', 'Marketplace',
]


def test_every_offline_l3_node_resolves_to_full_classification():
    for l3_name in OFFLINE_L3_NODES:
        result = rt.classify_by_taxonomy_node(l3_name, l3_name)
        assert result['gics_sector'] is not None, l3_name
        assert result['retail_subsector'] is not None, l3_name
        assert result['retail_format'] == l3_name
        assert result['channel_type'] == 'Retail'


def test_deepest_leaf_under_offline_subtree_keeps_leaf_as_retail_format():
    # Circle K's derived deepest category: leaf "Convenience Stores" (L4)
    # under L3 ancestor "Convenience Retailers".
    result = rt.classify_by_taxonomy_node('Convenience Stores', 'Convenience Retailers')
    assert result['retail_format'] == 'Convenience Stores'
    assert result['gics_sector'] == 'Consumer Staples'
    assert result['channel_type'] == 'Retail'

    # Pharmacity: leaf "Pharmacies" under L3 "Health and Beauty Specialists".
    result = rt.classify_by_taxonomy_node('Pharmacies', 'Health and Beauty Specialists')
    assert result['retail_format'] == 'Pharmacies'
    assert result['channel_type'] == 'Retail'


def test_channel_branch_nodes_are_rejected_not_misclassified():
    # These sit outside the Grocery/Non-Grocery offline subtree — the
    # documented ~21% misclassification trap. classify_by_taxonomy_node must
    # return all-None rather than inventing a retail format for a channel leaf.
    for l3_name in CHANNEL_L3_NODES:
        result = rt.classify_by_taxonomy_node(l3_name, l3_name)
        assert result == {
            'gics_sector': None, 'retail_subsector': None,
            'retail_format': None, 'channel_type': None,
        }, l3_name


def test_every_live_folder_subsector_resolves_to_non_none_result():
    for subsector in LIVE_FOLDER_SUBSECTORS:
        result = rt.classify_by_folder(subsector)
        assert result['gics_sector'] is not None, subsector
        assert result['retail_subsector'] is not None, subsector
        assert result['retail_format'] is not None, subsector
        assert result['channel_type'] is not None, subsector


def test_foodservice_subsectors_are_tagged_foodservice_not_retail():
    foodservice_slugs = [
        'coffee_chains', 'milktea', 'fast_food_chains', 'restaurant_chains', 'food_chain',
    ]
    for subsector in foodservice_slugs:
        result = rt.classify_by_folder(subsector)
        assert result['channel_type'] == 'Foodservice', subsector
        assert result['retail_subsector'] == 'Consumer Foodservice', subsector


def test_grocery_retail_subsectors_are_tagged_retail_not_foodservice():
    retail_slugs = ['convenience_stores', 'supermarket', 'hyper_supermarket', 'mini_supermarket']
    for subsector in retail_slugs:
        result = rt.classify_by_folder(subsector)
        assert result['channel_type'] == 'Retail', subsector


def test_services_subsectors_are_tagged_services():
    services_slugs = ['shopping_malls', 'movie_theatres', 'fitness_stores']
    for subsector in services_slugs:
        result = rt.classify_by_folder(subsector)
        assert result['channel_type'] == 'Services', subsector


def test_unknown_subsector_returns_all_none():
    result = rt.classify_by_folder('not_a_real_subsector')
    assert result == {
        'gics_sector': None, 'retail_subsector': None,
        'retail_format': None, 'channel_type': None,
    }


def test_unknown_l3_node_returns_all_none():
    result = rt.classify_by_taxonomy_node('Some Future Category', 'Some Future Category')
    assert result == {
        'gics_sector': None, 'retail_subsector': None,
        'retail_format': None, 'channel_type': None,
    }


def test_folder_crosswalk_lands_on_same_namespace_as_node_derivation():
    # convenience_stores (VN folder) must resolve to the SAME retail_format
    # a brand like Circle K would derive — one global namespace, not two
    # parallel vocabularies.
    folder_result = rt.classify_by_folder('convenience_stores')
    node_result = rt.classify_by_taxonomy_node('Convenience Stores', 'Convenience Retailers')
    assert folder_result['retail_format'] == node_result['retail_format'] == 'Convenience Stores'
    assert folder_result['gics_sector'] == node_result['gics_sector']
    assert folder_result['retail_subsector'] == node_result['retail_subsector']
