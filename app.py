from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

DB = "shop.db"

app = Flask(__name__)
app.secret_key = "mlsc_premium_secret_key"

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cur = con.cursor()
    # users
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )""")
    # categories
    cur.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")
    # products
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price REAL,
        image TEXT,
        category_id INTEGER,
        FOREIGN KEY(category_id) REFERENCES categories(id)
    )""")
    # orders
    cur.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        total REAL,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    # order_items
    cur.execute("""CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        qty INTEGER,
        price REAL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")
    con.commit()
    # create a default admin if not exists
    cur.execute("SELECT * FROM users WHERE username=?", ("admin",))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username,password,is_admin) VALUES (?,?,?)",
                    ("admin", generate_password_hash("admin123"), 1))
    # default categories and products
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("Clothing",))
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("Footwear",))
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("Accessories",))
    con.commit()
    # sample products (INSERT OR IGNORE by name is tricky; use existence check)
    cur.execute("SELECT COUNT(*) as cnt FROM products")
    if cur.fetchone()["cnt"] == 0:
        cur.executemany("INSERT INTO products (name,description,price,image,category_id) VALUES (?,?,?,?,?)", [
            ("Classic T-Shirt","Comfortable cotton t-shirt",599,"tshirt.jpg",1),
            ("Blue Jeans","Stylish denim jeans",1499,"jeans.jpg",1),
            ("Running Shoes","Lightweight running shoes",2499,"shoes.jpg",2),
            ("Baseball Cap","Adjustable cap",349,"cap.jpg",3),
        ])
        con.commit()
    con.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.","warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in as admin.","warning")
            return redirect(url_for("login"))
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT is_admin FROM users WHERE id=?", (session["user_id"],))
        row = cur.fetchone()
        con.close()
        if not row or row["is_admin"] != 1:
            flash("Admin access required.","danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index():
    q = request.args.get("q","").strip()
    cat = request.args.get("category","")
    con = get_db()
    cur = con.cursor()
    cats = cur.execute("SELECT * FROM categories").fetchall()
    query = "SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE 1=1"
    params = []
    if q:
        query += " AND p.name LIKE ?"
        params.append(f"%{q}%")
    if cat:
        query += " AND c.id = ?"
        params.append(cat)
    products = cur.execute(query, params).fetchall()
    con.close()
    return render_template("index.html", products=products, categories=cats, q=q, selected_cat=cat)

@app.route("/product/<int:pid>")
def product_detail(pid):
    con = get_db()
    cur = con.cursor()
    product = cur.execute("SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=?", (pid,)).fetchone()
    con.close()
    if not product:
        flash("Product not found.","danger")
        return redirect(url_for("index"))
    return render_template("product.html", p=product)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("Provide username and password.","warning")
            return redirect(url_for("signup"))
        con = get_db()
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO users (username,password) VALUES (?,?)", (username, generate_password_hash(password)))
            con.commit()
            flash("Account created. Please login.","success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("Username already exists.","danger")
            return redirect(url_for("signup"))
        finally:
            con.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        con.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Logged in successfully.","success")
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
        flash("Invalid credentials.","danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.","info")
    return redirect(url_for("index"))

@app.route("/add_to_cart/<int:pid>")
@login_required
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    flash("Added to cart.","success")
    return redirect(request.referrer or url_for("index"))

@app.route("/cart")
@login_required
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0
    if cart:
        con = get_db()
        cur = con.cursor()
        ids = list(map(int, cart.keys()))
        q = "SELECT * FROM products WHERE id IN ({seq})".format(seq=",".join(["?"]*len(ids)))
        rows = cur.execute(q, ids).fetchall()
        for r in rows:
            qty = cart.get(str(r["id"]), 0)
            subtotal = r["price"] * qty
            items.append({"product": r, "qty": qty, "subtotal": subtotal})
            total += subtotal
        con.close()
    return render_template("cart.html", items=items, total=total)

@app.route("/clear_cart")
@login_required
def clear_cart():
    session.pop("cart", None)
    flash("Cart cleared.","info")
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Cart empty.","warning")
        return redirect(url_for("index"))
    con = get_db()
    cur = con.cursor()
    ids = list(map(int, cart.keys()))
    q = "SELECT * FROM products WHERE id IN ({seq})".format(seq=",".join(["?"]*len(ids)))
    rows = cur.execute(q, ids).fetchall()
    total = 0
    for r in rows:
        total += r["price"] * cart.get(str(r["id"]), 0)
    created_at = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO orders (user_id,total,created_at) VALUES (?,?,?)", (session["user_id"], total, created_at))
    order_id = cur.lastrowid
    for r in rows:
        cur.execute("INSERT INTO order_items (order_id,product_id,qty,price) VALUES (?,?,?,?)",
                    (order_id, r["id"], cart.get(str(r["id"]), 0), r["price"]))
    con.commit()
    con.close()
    session.pop("cart", None)
    flash("Order placed successfully.","success")
    return redirect(url_for("orders"))

@app.route("/orders")
@login_required
def orders():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (session["user_id"],))
    orders = cur.fetchall()
    orders_data = []
    for o in orders:
        cur.execute("SELECT oi.*, p.name FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (o["id"],))
        items = cur.fetchall()
        orders_data.append({"order": o, "items": items})
    con.close()
    return render_template("orders.html", orders=orders_data)

# Admin routes
@app.route("/admin")
@admin_required
def admin_panel():
    con = get_db()
    cur = con.cursor()
    products = cur.execute("SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id").fetchall()
    cats = cur.execute("SELECT * FROM categories").fetchall()
    con.close()
    return render_template("admin.html", products=products, categories=cats)

@app.route("/admin/add_product", methods=["GET","POST"])
@admin_required
def add_product():
    con = get_db()
    cur = con.cursor()
    if request.method=="POST":
        name = request.form["name"].strip()
        desc = request.form["description"].strip()
        price = float(request.form["price"])
        image = request.form.get("image","placeholder.png").strip()
        cat = request.form.get("category")
        cur.execute("INSERT INTO products (name,description,price,image,category_id) VALUES (?,?,?,?,?)",
                    (name,desc,price,image,cat))
        con.commit()
        con.close()
        flash("Product added.","success")
        return redirect(url_for("admin_panel"))
    cats = cur.execute("SELECT * FROM categories").fetchall()
    con.close()
    return render_template("add_product.html", categories=cats)

@app.route("/admin/edit_product/<int:pid>", methods=["GET","POST"])
@admin_required
def edit_product(pid):
    con = get_db()
    cur = con.cursor()
    if request.method=="POST":
        name = request.form["name"].strip()
        desc = request.form["description"].strip()
        price = float(request.form["price"])
        image = request.form.get("image","placeholder.png").strip()
        cat = request.form.get("category")
        cur.execute("UPDATE products SET name=?,description=?,price=?,image=?,category_id=? WHERE id=?",
                    (name,desc,price,image,cat,pid))
        con.commit()
        con.close()
        flash("Product updated.","success")
        return redirect(url_for("admin_panel"))
    product = cur.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    cats = cur.execute("SELECT * FROM categories").fetchall()
    con.close()
    if not product:
        flash("Product not found.","danger")
        return redirect(url_for("admin_panel"))
    return render_template("edit_product.html", p=product, categories=cats)

@app.route("/admin/delete_product/<int:pid>")
@admin_required
def delete_product(pid):
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (pid,))
    con.commit()
    con.close()
    flash("Product deleted.","info")
    return redirect(url_for("admin_panel"))

@app.route("/admin/add_category", methods=["POST"])
@admin_required
def add_category():
    name = request.form.get("name","").strip()
    if name:
        con = get_db()
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        con.commit()
        con.close()
        flash("Category added.","success")
    return redirect(url_for("admin_panel"))

if __name__=="__main__":
    init_db()
    app.run(debug=True)
