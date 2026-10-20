<?php
/**
 * Plugin Name: S2Q Order Meta (sample-to-quote)
 * Description: Saves the product page's sample / quote fields onto order line items under fixed keys,
 *              so the order.created webhook carries them to the integration service.
 *
 * SKELETON / SPEC: not run against Perennials' WordPress. Install as a must-use plugin
 * (wp-content/mu-plugins/) on staging first. Handoff item W2.
 *
 * The product page already posts these fields with "Add Sample To Cart" / "Request A Quote":
 *   sampleProjectType[], length, lengthUnit, dateNeeded, cfa[], projectName, projectType[], comment
 * Verify the exact POST names on staging (they were read from the live page's HTML).
 */

defined('ABSPATH') || exit;

const S2Q_META = [
    // POST field          => order item meta key
    'sampleProjectType' => '_s2q_project_type',
    'projectType'       => '_s2q_project_type',
    'length'            => '_s2q_length',
    'lengthUnit'        => '_s2q_length_unit',   // yards | feet | meters
    'dateNeeded'        => '_s2q_date_needed',   // ISO date
    'cfa'               => '_s2q_cfa',           // requested | waived
    'projectName'       => '_s2q_project_name',
    'comment'           => '_s2q_comment',
];

/**
 * 1) Add to cart: copy the posted fields into the cart item, and record which button was used.
 *    Hook: woocommerce_add_cart_item_data (filter).
 */
add_filter('woocommerce_add_cart_item_data', function (array $cart_item_data, int $product_id, int $variation_id) {
    // TODO: decide line type from the button / form that posted (sample vs quote).
    //       e.g. $_POST['type'] or a hidden field the theme sets; '_s2q_line_type' => 'sample' | 'quote'.
    // TODO: for each S2Q_META field present in $_POST, sanitize (sanitize_text_field; radios arrive as arrays,
    //       take the first value) and store under $cart_item_data['s2q'][$meta_key].
    // TODO: two identical variations with different project data must stay separate lines:
    //       set $cart_item_data['unique_key'] = md5(json_encode($cart_item_data['s2q'])).
    return $cart_item_data;
}, 10, 3);

/**
 * 2) Checkout: move the cart item data onto the order line item as meta.
 *    Hook: woocommerce_checkout_create_order_line_item (action).
 */
add_action('woocommerce_checkout_create_order_line_item', function ($item, $cart_item_key, $values, $order) {
    // TODO: foreach ($values['s2q'] ?? [] as $key => $value) { $item->add_meta_data($key, $value, true); }
    // Variation SKU must equal the NetSuite item id (handoff item W1); nothing to copy for that.
}, 10, 4);

/**
 * 3) Optional (handoff W4): once the service matches a logged-in customer to a Salesforce Contact,
 *    it can write `_sf_contact_id` user meta through the WP REST API so repeat orders match exactly.
 */
