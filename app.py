from flask import Flask, request, redirect, render_template, url_for, make_response
import sqlite3
import uuid

app = Flask(__name__)

DATABASE = 'database.db'

sessions = {}

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    session_id = request.cookies.get('session_id')

    if not session_id:
        session_id = str(uuid.uuid4())
        resp = make_response(render_template('index.html'))
        resp.set_cookie('session_id', session_id, path='/')
        return resp

    if session_id in sessions:
        return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and user['password'] == password:
            session_id = request.cookies.get('session_id')
            if not session_id:
                session_id = str(uuid.uuid4())
            
            sessions[session_id] = username
            resp = make_response(redirect(url_for('dashboard')))
            resp.set_cookie('session_id', session_id, path='/')
            return resp
        else:
            error = "Invalid login"

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session_id = request.cookies.get('session_id')
    
    if session_id and session_id in sessions:
        sessions.pop(session_id) 
    
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('session_id', '', expires=0, path='/')
    return resp

@app.route('/dashboard')
def dashboard():
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return redirect(url_for('login'))
    
    username = sessions[session_id]
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if not user:
        return "User not found", 404

    transactions = conn.execute('''
        SELECT sender, recipient, amount, timestamp
        FROM messages
        WHERE sender = ? OR recipient = ?
        ORDER BY timestamp DESC
        LIMIT 3
    ''', (username, username)).fetchall()

    conn.close()

    formatted_transactions = []
    for transaction in transactions:
        amount = transaction['amount']
        if transaction['sender'] == username:
            formatted_transactions.append(f"💸 Sent ${amount} to {transaction['recipient']}")
        else:
            formatted_transactions.append(f"💰 Received ${amount} from {transaction['sender']}")

    return render_template('dashboard.html', username=username, balance=user['balance'], transactions=formatted_transactions)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password, balance) VALUES (?, ?, ?)', 
                         (username, password, 0.0))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Username already taken!", 409
        
        conn.close()
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return redirect(url_for('login'))

    current_user = sessions[session_id]
    conn = get_db_connection()

    contacts = conn.execute('''
        SELECT DISTINCT
            CASE 
                WHEN sender = ? THEN recipient
                WHEN recipient = ? THEN sender
            END AS contact
        FROM messages
        WHERE sender = ? OR recipient = ?
    ''', (current_user, current_user, current_user, current_user)).fetchall()

    conn.close()

    error = None

    if request.method == 'POST':
        sender = request.form['sender']  
        recipient = request.form['recipient']
        amount = float(request.form['amount'])
        message = request.form['message']

        conn = get_db_connection()
        sender_user = conn.execute('SELECT * FROM users WHERE username = ?', (sender,)).fetchone()
        recipient_user = conn.execute('SELECT * FROM users WHERE username = ?', (recipient,)).fetchone()

        if not sender_user or not recipient_user:
            conn.close()
            error = "Sender or recipient not found"
        elif sender_user['balance'] < amount:
            conn.close()
            error = "Insufficient funds"
        elif amount < 0:
            conn.close()
            error = "Amount cannot be negative"
        else:
            conn.execute('UPDATE users SET balance = balance - ? WHERE username = ?', (amount, sender))
            conn.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, recipient))
            conn.execute(
                'INSERT INTO messages (sender, recipient, amount, message) VALUES (?, ?, ?, ?)',
                (sender, recipient, amount, message)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard'))

    return render_template('transfer.html', contacts=contacts, error=error, current_user=current_user)



@app.route('/conversation/<contact>')
def conversation(contact):
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return redirect(url_for('login'))

    current_user = sessions[session_id]

    conn = get_db_connection()
    messages = conn.execute('''
        SELECT sender, recipient, amount, message, timestamp
        FROM messages
        WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
        ORDER BY timestamp ASC
    ''', (current_user, contact, contact, current_user)).fetchall()
    conn.close()

    return render_template('conversation.html', contact=contact, messages=messages, current_user=current_user)


if __name__ == '__main__':
    app.run(debug=True)
