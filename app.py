import os
import xmlrpc.client
import yaml
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

app = Flask(__name__)

# ── Load config from environment ──────────────────────────────────────────────
ODOO_URL   = os.getenv("ODOO_URL")
ODOO_DB    = os.getenv("ODOO_DB")
ODOO_EMAIL = os.getenv("ODOO_EMAIL")
ODOO_KEY   = os.getenv("ODOO_API_KEY")
APP_KEY    = os.getenv("APP_API_KEY")

# ── Load field mappings from your YAML ────────────────────────────────────────
with open("mapping.yaml", "r") as f:
    config = yaml.safe_load(f)

CUSTOMER_MAP = config["customer"]   # name, email, phone, address
PRODUCT_MAP  = config["product"]    # name, price, description, code
ORDER_MAP    = config["order"]      # customer_id, date, status, reference


# ── The Mapper Class ───────────────────────────────────────────────────────────
class ERPDataMapper:
    """
    Translates incoming JSON keys into Odoo-specific field names
    using the mapping.yaml config file.

    Example:
        Input:  {"address": "123 Nairobi St"}
        Output: {"street": "123 Nairobi St"}
    """
    def __init__(self, mapping_dict: dict):
        self.mapping = mapping_dict

    def transform(self, data: dict) -> dict:
        """Only keeps fields that exist in the mapping config."""
        return {
            self.mapping[k]: v
            for k, v in data.items()
            if k in self.mapping
        }


# ── Odoo XML-RPC Connection ───────────────────────────────────────────────────
def get_odoo_connection():
    """
    Authenticates with Odoo via XML-RPC.
    Returns (uid, models) — uid is your user ID, models lets you query Odoo.
    """
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_EMAIL, ODOO_KEY, {})

    if not uid:
        raise ConnectionError("Odoo authentication failed. Check your .env credentials.")

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


# ── API Key Protection ─────────────────────────────────────────────────────────
def require_api_key(f):
    """Blocks requests that don't include the correct X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if key != APP_KEY:
            return jsonify({"error": "Unauthorized. Provide a valid X-API-Key header."}), 401
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/customers", methods=["GET"])
@require_api_key
def get_customers():
    """
    Retrieves all customers from Odoo (res.partner).

    Returns their id, name, email, phone, and street address —
    matching the fields defined in your customer mapping.
    """
    uid, models = get_odoo_connection()

    customers = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "res.partner", "search_read",
        [[["customer_rank", ">", 0]]],
        {
            # Use the Odoo field names (right side of your customer mapping)
            "fields": ["id", "name", "email", "phone", "street"],
            "limit": 100
        }
    )

    return jsonify({"total": len(customers), "customers": customers}), 200


@app.route("/customers", methods=["POST"])
@require_api_key
def create_customer():
    """
    Creates a new customer in Odoo (res.partner).

    Expected JSON body:
    {
        "name":    "Jane Doe",
        "email":   "jane@example.com",
        "phone":   "+254700000000",
        "address": "123 Nairobi Street"   <-- maps to 'street' in Odoo
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No JSON body provided."}), 400

    # Validate that at minimum a name was provided
    if "name" not in payload:
        return jsonify({"error": "Customer 'name' is required."}), 400

    # Translate incoming keys to Odoo field names using your mapping
    mapper       = ERPDataMapper(CUSTOMER_MAP)
    odoo_data    = mapper.transform(payload)

    # Mark as a customer in Odoo (not just a contact)
    odoo_data["customer_rank"] = 1

    uid, models  = get_odoo_connection()
    customer_id  = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "res.partner", "create",
        [odoo_data]
    )

    return jsonify({
        "success":     True,
        "customer_id": customer_id,
        "message":     f"Customer created successfully with ID {customer_id}"
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/products", methods=["GET"])
@require_api_key
def get_products():
    """
    Retrieves all products from Odoo (product.template).

    Returns their id, name, list_price, description_sale, and default_code —
    matching the fields defined in your product mapping.
    """
    uid, models = get_odoo_connection()

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "product.template", "search_read",
        [[["sale_ok", "=", True]]],
        {
            # Use the Odoo field names (right side of your product mapping)
            "fields": ["id", "name", "list_price", "description_sale", "default_code"],
            "limit": 100
        }
    )

    return jsonify({"total": len(products), "products": products}), 200


@app.route("/products", methods=["POST"])
@require_api_key
def create_product():
    """
    Creates a new product in Odoo (product.template).

    Expected JSON body:
    {
        "name":        "Laptop",
        "price":       75000.00,    <-- maps to 'list_price' in Odoo
        "description": "High-end laptop",  <-- maps to 'description_sale'
        "code":        "LAP-001"    <-- maps to 'default_code' in Odoo
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No JSON body provided."}), 400

    if "name" not in payload:
        return jsonify({"error": "Product 'name' is required."}), 400

    mapper     = ERPDataMapper(PRODUCT_MAP)
    odoo_data  = mapper.transform(payload)

    uid, models = get_odoo_connection()
    product_id  = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "product.template", "create",
        [odoo_data]
    )

    return jsonify({
        "success":    True,
        "product_id": product_id,
        "message":    f"Product created successfully with ID {product_id}"
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  SALES ORDER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/orders", methods=["GET"])
@require_api_key
def get_orders():
    """
    Retrieves all Sales Orders from Odoo (sale.order).

    Returns their id, name (reference), partner_id (customer),
    date_order, and state — matching your order mapping.
    """
    uid, models = get_odoo_connection()

    orders = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "sale.order", "search_read",
        [[]],
        {
            # Use Odoo field names (right side of your order mapping)
            "fields": ["id", "name", "partner_id", "date_order", "state"],
            "limit": 100
        }
    )

    return jsonify({"total": len(orders), "orders": orders}), 200


@app.route("/orders", methods=["POST"])
@require_api_key
def create_order():
    """
    Creates a new Sales Order in Odoo (sale.order).

    Expected JSON body:
    {
        "customer_id": 7,                   <-- maps to 'partner_id' in Odoo
        "date":        "2025-06-01 10:00:00", <-- maps to 'date_order'
        "reference":   "ORD-2025-001",      <-- maps to 'name' in Odoo
        "status":      "draft",             <-- maps to 'state' (draft/sale/done)
        "order_lines": [
            {
                "product_id": 1,
                "product_uom_qty": 2,
                "price_unit": 1500.00
            }
        ]
    }

    Note: 'customer_id' must be a valid Odoo partner ID.
          Get one from GET /customers first.
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No JSON body provided."}), 400

    if "customer_id" not in payload:
        return jsonify({"error": "'customer_id' is required to create a Sales Order."}), 400

    # Translate order-level fields using your order mapping
    mapper     = ERPDataMapper(ORDER_MAP)
    odoo_data  = mapper.transform(payload)

    # Handle order lines — these go directly to Odoo without extra mapping
    # because they already use Odoo field names (product_id, qty, price_unit)
    raw_lines = payload.get("order_lines", [])
    if raw_lines:
        odoo_data["order_line"] = [
            (0, 0, line) for line in raw_lines
            # (0, 0, {...}) is Odoo's special format for creating nested records
        ]

    uid, models = get_odoo_connection()
    order_id    = models.execute_kw(
        ODOO_DB, uid, ODOO_KEY,
        "sale.order", "create",
        [odoo_data]
    )

    return jsonify({
        "success":  True,
        "order_id": order_id,
        "message":  f"Sales Order created successfully with ID {order_id}"
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health_check():
    """Quick check to confirm the middleware is running."""
    return jsonify({"status": "ok", "service": "Odoo Middleware"}), 200


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)