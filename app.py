from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
DATABASE = 'helping_hand.db'

app = Flask(__name__)
app.secret_key = 'super-secret-key-v3'

# Make Python's enumerate available in Jinja templates (fixes "enumerate is undefined")
app.jinja_env.globals.update(enumerate=enumerate)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db(seed_demo=True):
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        cur = db.execute("SELECT COUNT(*) as c FROM users")
        c = cur.fetchone()['c']
        if seed_demo and c == 0:
            # seed users
            users = [
                ('Ram Kumar','ram@example.com', generate_password_hash('pass123'), 'Harvesting, Farming', 'worker'),
                ('Sita Devi','sita@example.com', generate_password_hash('pass123'), 'Tailoring, Sewing', 'worker'),
                ('Munna','munna@example.com', generate_password_hash('pass123'), 'Plumbing, Repair', 'worker'),
                ('Tanu','tanu@example.com', generate_password_hash('pass123'), 'Gardening, Cleaning', 'worker'),
                ('Aman','aman@example.com', generate_password_hash('pass123'), 'Carpentry, Building', 'worker'),
            ]
            for u in users:
                db.execute("INSERT INTO users (name,email,password,skills,role,created_at) VALUES (?,?,?,?,?,?)", (*u, datetime.utcnow()))
            db.execute("INSERT INTO users (name,email,password,skills,role,created_at) VALUES (?,?,?,?,?,?)",
                       ('Admin','admin@helpinghand.local', generate_password_hash('admin123'), '', 'admin', datetime.utcnow()))
            # tasks
            tasks = [
                ('Harvesting in the fields','Help with harvesting wheat for 1 day','500',1,'open'),
                ('Repairing a water pump','Fix the village water pump motor','400',3,'open'),
                ('Gardening','Trim and maintain the community garden','500',4,'open'),
                ('Building a shed','Build a small storage shed','1500',5,'open'),
                ('Cleaning community hall','Deep cleaning before event','500',2,'open'),
                ('Paint the school wall','Paint two classroom walls','1200',1,'open'),
                ('Fix door hinges','Fix and oil door hinges','300',3,'open'),
            ]
            for t in tasks:
                db.execute("INSERT INTO tasks (title,description,budget,user_id,status,created_at) VALUES (?,?,?,?,?,?)", (*t, datetime.utcnow()))
            # reviews
            db.execute("INSERT INTO reviews (user_id, reviewer_name, rating, comment, created_at) VALUES (?,?,?,?,?)",
                       (1, 'Villager A', 5, 'Very hard worker and on time', datetime.utcnow()))
            db.execute("INSERT INTO reviews (user_id, reviewer_name, rating, comment, created_at) VALUES (?,?,?,?,?)",
                       (2, 'Villager B', 4, 'Good tailoring skills', datetime.utcnow()))
            # notifications
            db.execute("INSERT INTO notifications (user_id, message, is_read, created_at) VALUES (?,?,?,?)",
                       (1, 'You have a new hire request for \"Harvesting in the fields\"', 0, datetime.utcnow()))
            db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid

@app.route('/')
def index():
    featured = query_db('SELECT t.*, u.name as poster_name FROM tasks t LEFT JOIN users u ON t.user_id = u.id ORDER BY t.id DESC LIMIT 3')
    tasks = query_db('SELECT t.*, u.name as poster_name FROM tasks t LEFT JOIN users u ON t.user_id = u.id ORDER BY t.created_at DESC LIMIT 6')
    stories = query_db('SELECT * FROM users WHERE role = ? LIMIT 3', ('worker',))
    return render_template('index.html', featured=featured, tasks=tasks, stories=stories)

@app.route('/search')
def search():
    q = request.args.get('q','').strip()
    skill = request.args.get('skill','').strip()
    minb = request.args.get('minb','')
    maxb = request.args.get('maxb','')
    sql = 'SELECT t.*, u.name as poster_name FROM tasks t LEFT JOIN users u ON t.user_id = u.id WHERE 1=1'
    args = []
    if q:
        sql += ' AND (t.title LIKE ? OR t.description LIKE ?)'
        args += [f'%{q}%', f'%{q}%']
    if skill:
        sql += ' AND u.skills LIKE ?'
        args += [f'%{skill}%']
    if minb:
        sql += ' AND CAST(t.budget AS INTEGER) >= ?'
        args += [minb]
    if maxb:
        sql += ' AND CAST(t.budget AS INTEGER) <= ?'
        args += [maxb]
    sql += ' ORDER BY t.created_at DESC'
    tasks = query_db(sql, args)
    return render_template('tasks.html', tasks=tasks)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name = request.form['name']; email = request.form['email']; password = request.form['password']; skills = request.form.get('skills','')
        if not name or not email or not password:
            flash('Please fill all fields','danger'); return redirect(url_for('register'))
        if query_db('SELECT * FROM users WHERE email = ?', (email,), one=True):
            flash('Email already registered','warning'); return redirect(url_for('register'))
        pw = generate_password_hash(password)
        execute_db('INSERT INTO users (name,email,password,skills,role,created_at) VALUES (?,?,?,?,?,?)', (name,email,pw,skills,'worker', datetime.utcnow()))
        flash('Registered successfully. Please login.','success'); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email']; password = request.form['password']
        user = query_db('SELECT * FROM users WHERE email = ?', (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']; session['user_name'] = user['name']; session['role'] = user['role']
            # admin logging
            if user['role']=='admin':
                execute_db('INSERT INTO admin_logs (admin_id, action, created_at) VALUES (?,?,?)', (user['id'], 'login', datetime.utcnow()))
            flash('Logged in successfully','success')
            return redirect(url_for('dashboard') if user['role']=='admin' else url_for('index'))
        flash('Invalid credentials','danger'); return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out','info'); return redirect(url_for('index'))

@app.route('/post-task', methods=['GET','POST'])
def post_task():
    if 'user_id' not in session:
        flash('Please login to post','warning'); return redirect(url_for('login'))
    if request.method=='POST':
        title = request.form['title']; description = request.form['description']; budget = request.form['budget'] or '0'
        execute_db('INSERT INTO tasks (title,description,budget,user_id,status,created_at) VALUES (?,?,?,?,?,?)', (title,description,budget, session['user_id'],'open', datetime.utcnow()))
        flash('Task posted','success'); return redirect(url_for('index'))
    return render_template('post_task.html')

@app.route('/tasks')
def tasks():
    tasks = query_db('SELECT t.*, u.name as poster_name FROM tasks t LEFT JOIN users u ON t.user_id = u.id ORDER BY t.created_at DESC')
    return render_template('tasks.html', tasks=tasks)

@app.route('/task/<int:task_id>')
def task_detail(task_id):
    task = query_db('SELECT t.*, u.name as poster_name, u.skills FROM tasks t LEFT JOIN users u ON t.user_id = u.id WHERE t.id = ?', (task_id,), one=True)
    return render_template('task_detail.html', task=task)

@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
    reviews = query_db('SELECT * FROM reviews WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    avg = query_db('SELECT AVG(rating) as avg FROM reviews WHERE user_id = ?', (user_id,), one=True)['avg'] or 0
    return render_template('profile.html', user=user, reviews=reviews, avg=round(avg,1))

@app.route('/review/<int:user_id>', methods=['POST'])
def review(user_id):
    name = request.form.get('name') or session.get('user_name','Anonymous')
    rating = int(request.form.get('rating',5)); comment = request.form.get('comment','')
    execute_db('INSERT INTO reviews (user_id, reviewer_name, rating, comment, created_at) VALUES (?,?,?,?,?)', (user_id, name, rating, comment, datetime.utcnow()))
    flash('Thank you for rating','success'); return redirect(url_for('profile', user_id=user_id))

@app.route('/hire/<int:task_id>', methods=['GET','POST'])
def hire(task_id):
    if 'user_id' not in session:
        flash('Please login to hire','warning'); return redirect(url_for('login'))
    task = query_db('SELECT * FROM tasks WHERE id = ?', (task_id,), one=True)
    if request.method=='POST':
        hired_user = int(request.form['hired_user'])
        execute_db('INSERT INTO hires (task_id, hired_user_id, hirer_user_id, status, created_at) VALUES (?,?,?,?,?)', (task_id, hired_user, session['user_id'], 'pending', datetime.utcnow()))
        execute_db('UPDATE tasks SET status = ? WHERE id = ?', ('assigned', task_id))
        # create notification for hired user
        execute_db('INSERT INTO notifications (user_id, message, is_read, created_at) VALUES (?,?,?,?)', (hired_user, f'You have a new hire request for \"{task["title"]}\"', 0, datetime.utcnow()))
        flash('Hiring request sent','success'); return redirect(url_for('tasks'))
    workers = query_db('SELECT * FROM users WHERE role = ?', ('worker',))
    return render_template('hire.html', task=task, workers=workers)

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        flash('Please login to view notifications','warning'); return redirect(url_for('login'))
    notes = query_db('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],))
    return render_template('notifications.html', notes=notes)

@app.route('/notifications/markread/<int:nid>')
def mark_read(nid):
    execute_db('UPDATE notifications SET is_read = 1 WHERE id = ?', (nid,))
    return redirect(url_for('notifications'))

@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        flash('Admin access only','danger'); return redirect(url_for('login'))
    total_users = query_db('SELECT COUNT(*) as c FROM users', one=True)['c']
    total_tasks = query_db('SELECT COUNT(*) as c FROM tasks', one=True)['c']
    total_hires = query_db('SELECT COUNT(*) as c FROM hires', one=True)['c']
    recent_tasks = query_db('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 6')
    logs = query_db('SELECT l.*, u.name as admin_name FROM admin_logs l LEFT JOIN users u ON l.admin_id = u.id ORDER BY l.created_at DESC LIMIT 20')
    return render_template('admin.html', users=total_users, tasks=total_tasks, hires=total_hires, recent_tasks=recent_tasks, logs=logs)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login','warning'); return redirect(url_for('login'))
    user_tasks = query_db('SELECT * FROM tasks WHERE user_id = ?', (session['user_id'],))
    user_hires = query_db('SELECT * FROM hires WHERE hirer_user_id = ? OR hired_user_id = ?', (session['user_id'], session['user_id']))
    notes = query_db('SELECT * FROM notifications WHERE user_id = ? AND is_read = 0', (session['user_id'],))
    return render_template('dashboard.html', tasks=user_tasks, hires=user_hires, notes=notes)

@app.route('/initdb')
def initdb_route():
    init_db(seed_demo=True)
    flash('Database initialized with demo data (admin: admin@helpinghand.local / admin123)','info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db(seed_demo=True)
    app.run(debug=True)
