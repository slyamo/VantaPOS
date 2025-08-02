from flask import Flask, render_template, request, redirect, url_for, flash
from flask import session
from flask_mysqldb import MySQL
from flask import make_response
import csv
import io
from datetime import datetime
import calendar
import MySQLdb.cursors

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Load MySQL config
app.config.from_pyfile('config.py')

# Set cursor class to DictCursor
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

#user role
@app.context_processor
def inject_user_role():
    return dict(user_role=session.get('role'))


# Redirect root route to login
@app.route('/')
def index():
    return redirect(url_for('login'))

"""
@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            session['username'] = user['username']
            session['role'] = user['role']  # ✅ Store role in session
            flash('Login successful', 'success')
            return redirect(url_for('dashboard'))
        else:
            msg = 'Invalid credentials'

    return render_template('login.html', msg=msg)

"""
from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful', 'success')
            return redirect(url_for('dashboard'))
        else:
            msg = 'Invalid credentials'

    return render_template('login.html', msg=msg)


#Dashboard Route
@app.route('/dashboard')
def dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # === Total Sales & Profit for Today ===
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT SUM(o.total_price) AS total_sales
        FROM orders o
        WHERE DATE(o.order_date) = %s
    """, (today,))
    sales_result = cursor.fetchone()
    total_sales = sales_result['total_sales'] or 0

    cursor.execute("""
        SELECT oi.product_id, oi.quantity, p.selling_price, p.buying_price
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN products p ON oi.product_id = p.id
        WHERE DATE(o.order_date) = %s
    """, (today,))
    items = cursor.fetchall()

    total_profit = 0
    for item in items:
        profit_per_item = (item['selling_price'] - item['buying_price']) * item['quantity']
        total_profit += profit_per_item

    # === Low Stock Products ===
    cursor.execute("SELECT name, stock FROM products WHERE stock < threshold")
    low_stock = cursor.fetchall()

    # === Monthly Sales Data ===
    cursor.execute("""
        SELECT DATE_FORMAT(order_date, '%Y-%m') AS month, 
               SUM(total_price) AS total
        FROM orders
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6

    """)

    monthly_data = cursor.fetchall()

    months = []
    totals = []
    for row in monthly_data:
        print(row['month'])
        try:
            month_name = datetime.strptime(row['month'], "%Y-%m").strftime("%B")
        except Exception:
            month_name = row['month']
        months.append(month_name)
        totals.append(float(row['total']))

        # === Pie chart Most sold products ===
        cursor.execute("""
            SELECT p.name, SUM(oi.quantity) AS total_sold
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE MONTH(o.order_date) = MONTH(CURDATE())
              AND YEAR(o.order_date) = YEAR(CURDATE())
            GROUP BY p.name
            ORDER BY total_sold DESC
            LIMIT 5
        """)
        pie_data = cursor.fetchall()

        # Prepare data for Chart.js
        product_names = [row['name'] for row in pie_data]
        quantities_sold = [row['total_sold'] for row in pie_data]

    return render_template('dashboard.html',
                           total_sales=total_sales,
                           total_profit=total_profit,
                           low_stock=low_stock,
                           months=months,
                           monthly_totals=totals,
                           product_names=product_names,
                           quantities_sold=quantities_sold
                           )


# Products page route
@app.route('/products')
def products():
    query = request.args.get('query', '').strip()

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if query:
        cursor.execute("""
            SELECT * FROM products
            WHERE name LIKE %s OR category LIKE %s
        """, (f"%{query}%", f"%{query}%"))
    else:
        cursor.execute("SELECT * FROM products")

    products = cursor.fetchall()
    cursor.close()
    return render_template('products.html', products=products)


#add product route
@app.route('/add-product', methods=['POST'])
def add_product():
    try:
        name = request.form['name']
        category = request.form['category']
        buying_price = float(request.form['buying_price'])
        selling_price = float(request.form['selling_price'])
        stock = int(request.form['stock'])
        threshold = int(request.form['threshold'])

        # Backend validation
        if buying_price < 0 or selling_price < 0 or stock < 0 or threshold < 0:
            flash("Prices, stock, and threshold must be non-negative.", "error")
            return redirect(url_for('products'))

        # Insert into database (adjust table/column names as needed)
        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO products (name, category, buying_price, selling_price, stock, threshold)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, category, buying_price, selling_price, stock, threshold))
        mysql.connection.commit()
        cursor.close()

        flash("Product added successfully!", "success")
        return redirect(url_for('products'))

    except Exception as e:
        flash(f"Error: {str(e)}", "error")
        return redirect(url_for('products'))

#edit product route
@app.route('/edit-product', methods=['POST'])
def edit_product():
    try:
        product_id = request.form['product_id']
        name = request.form['name']
        category = request.form['category']
        buying_price = float(request.form['buying_price'])
        selling_price = float(request.form['selling_price'])
        stock = int(request.form['stock'])
        threshold = int(request.form['threshold'])

        if buying_price < 0 or selling_price < 0 or stock < 0 or threshold < 0:
            flash("Values must be non-negative.", "error")
            return redirect(url_for('products'))

        cursor = mysql.connection.cursor()
        cursor.execute("""
            UPDATE products
            SET name = %s, category = %s, buying_price = %s, selling_price = %s, stock = %s, threshold = %s
            WHERE id = %s
        """, (name, category, buying_price, selling_price, stock, threshold, product_id))
        mysql.connection.commit()
        cursor.close()

        flash("Product updated successfully!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "error")

    return redirect(url_for('products'))

#delete product route
@app.route('/delete-product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        mysql.connection.commit()
        cursor.close()

        flash("Product deleted successfully!", "success")
    except Exception as e:
        flash(f"Error deleting product: {str(e)}", "error")

    return redirect(url_for('products'))


# Orders Page Route
@app.route('/orders')
def orders():
    cursor = mysql.connection.cursor()

    # Fetch all orders
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()

    # Fetch all products
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    cursor.close()
    return render_template('orders.html', orders=orders, products=products)


@app.route('/add_order', methods=['POST'])
def add_order():
    from datetime import datetime

    customer = request.form['customer']
    total = request.form.get('total', 0)
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor = mysql.connection.cursor()

    # Insert order record
    cursor.execute("""
        INSERT INTO orders (customer_name, order_date, total_price)
        VALUES (%s, %s, %s)
    """, (customer, date, total))
    order_id = cursor.lastrowid

    # Handle selected products
    product_ids = request.form.getlist('product_ids')
    for product_id in product_ids:
        quantity = int(request.form.get(f'quantities_{product_id}', 1))

        # Insert into order_items
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity)
            VALUES (%s, %s, %s)
        """, (order_id, product_id, quantity))

        # Reduce stock in products table
        cursor.execute("""
            UPDATE products
            SET stock = stock - %s
            WHERE id = %s AND stock >= %s
        """, (quantity, product_id, quantity))

    mysql.connection.commit()
    cursor.close()

    flash('Order added and stock updated!', 'success')
    return redirect(url_for('orders'))



@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
    mysql.connection.commit()
    cursor.close()
    flash("Order deleted successfully", "success")
    return redirect(url_for('orders'))



#settings route
@app.route('/settings')
def settings():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    # Fetch all users
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT id, username, role FROM users')
    users = cursor.fetchall()
    cursor.close()

    return render_template('settings.html', users=users)

#update role route
@app.route('/update_role', methods=['POST'])
def update_role():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    user_id = request.form['user_id']
    new_role = request.form['role']

    cursor = mysql.connection.cursor()
    cursor.execute('UPDATE users SET role = %s WHERE id = %s', (new_role, user_id))
    mysql.connection.commit()
    cursor.close()

    flash('User role updated successfully.', 'success')
    return redirect(url_for('settings'))

'''
#add user route
@app.route('/add_user', methods=['POST'])
def add_user():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    username = request.form['username']
    password = request.form['password']
    role = request.form['role']

    cursor = mysql.connection.cursor()
    cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, role))
    mysql.connection.commit()
    cursor.close()

    flash('User added successfully', 'success')
    return redirect(url_for('settings'))
'''

from werkzeug.security import generate_password_hash

@app.route('/add_user', methods=['POST'])
def add_user():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    username = request.form['username']
    password = request.form['password']
    role = request.form['role']

    # Hash the password before saving
    hashed_password = generate_password_hash(password)

    cursor = mysql.connection.cursor()
    cursor.execute(
        'INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
        (username, hashed_password, role)
    )
    mysql.connection.commit()
    cursor.close()

    flash('User added successfully', 'success')
    return redirect(url_for('settings'))


'''
#delete user routep
@app.route('/delete_user', methods=['POST'])
def delete_user():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    user_id = request.form['user_id']

    cursor = mysql.connection.cursor()
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    mysql.connection.commit()
    cursor.close()

    flash('User deleted successfully', 'success')
    return redirect(url_for('settings'))
'''

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if 'role' not in session or session['role'] != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    user_id = request.form['user_id']

    try:
        cursor = mysql.connection.cursor()
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        mysql.connection.commit()
        flash('User deleted successfully', 'success')
    except Exception as e:
        flash('An error occurred while deleting the user.', 'danger')
    finally:
        cursor.close()

    return redirect(url_for('settings'))








#Reports Route
@app.route('/reports')
def reports():
    if 'role' not in session:
        return redirect(url_for('login'))

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query = """
        SELECT 
            p.name AS product_name,
            SUM(oi.quantity) AS total_quantity_sold,
            SUM(oi.quantity * p.selling_price) AS total_revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON o.id = oi.order_id
    """

    params = []
    if start_date and end_date:
        query += " WHERE o.created_at BETWEEN %s AND %s"
        params = [start_date + " 00:00:00", end_date + " 23:59:59"]

    query += " GROUP BY p.id ORDER BY total_quantity_sold DESC"

    cursor.execute(query, params)
    reports = cursor.fetchall()
    cursor.close()

    return render_template('reports.html', reports=reports)


#Help Route
@app.route('/help')
def help():
    return render_template('help.html')

#Export Reports
@app.route('/export_report')
def export_report():
    if 'role' not in session:
        return redirect(url_for('login'))

    start_date = request.args.get('start_date') or '2000-01-01'
    end_date = request.args.get('end_date') or '2100-01-01'
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query = """
        SELECT 
            p.name AS product_name,
            SUM(oi.quantity) AS total_quantity_sold,
            SUM(oi.quantity * p.selling_price) AS total_revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.created_at BETWEEN %s AND %s
        GROUP BY p.id
        ORDER BY total_quantity_sold DESC
    """

    cursor.execute(query, (start_date + " 00:00:00", end_date + " 23:59:59"))
    report_data = cursor.fetchall()
    cursor.close()

    # Create CSV
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Product', 'Total Quantity Sold', 'Total Revenue'])

    for row in report_data:
        cw.writerow([
            row['product_name'],
            row['total_quantity_sold'],
            "%.2f" % (row['total_revenue'] or 0)
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=report.csv"
    output.headers["Content-type"] = "text/csv"
    return output



if __name__ == '__main__':
    app.run(debug=True)
