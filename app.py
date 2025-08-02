from flask import Flask, render_template, request, redirect, session, url_for, send_file, make_response, flash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import os
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import timedelta
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.permanent_session_lifetime = timedelta(minutes=30)

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DATABASE_HOST'),
        database=os.getenv('DATABASE_NAME'),
        user=os.getenv('DATABASE_USER'),
        password=os.getenv('DATABASE_PASSWORD')

    )

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        session['user'] = username
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/download_pdf')
def download_pdf():
    if 'case_details' not in session:
        flash("No case details to download.")
        return redirect(url_for('dashboard'))

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica", 12)
    p.drawString(100, 750, "Case Details Report")
    p.drawString(100, 730, f"Court Name: {session['case_details'][1]}")
    p.drawString(100, 710, f"Case Type: {session['case_details'][2]}")
    p.drawString(100, 690, f"Case Number: {session['case_details'][3]}")
    p.drawString(100, 670, f"Submitted On: {session['case_details'][5]}")
    p.showPage()
    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='case_details.pdf', mimetype='application/pdf')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT court_name FROM case_queries ORDER BY court_name ASC")
    courts = [row[0] for row in cur.fetchall()]

    result = None
    case_details = None

    if request.method == 'POST':
        try:
            user_answer = int(request.form['captcha_answer'])
        except ValueError:
            flash("❌ Invalid CAPTCHA input.")
            return redirect(url_for('dashboard'))

        correct_answer = session.get('captcha_num1', 0) + session.get('captcha_num2', 0)

        if user_answer != correct_answer:
            flash("❌ CAPTCHA failed. Try again.")
            return redirect(url_for('dashboard'))

        court = request.form['court']
        case_type = request.form['case_type']
        case_number = request.form['case_number']

        cur.execute("""
            SELECT * FROM case_queries
            WHERE court_name = %s AND case_type = %s AND case_number = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (court, case_type, case_number))
        case_details = cur.fetchone()

        if case_details:
            session['latest_case'] = {
                'court': case_details[1],
                'case_type': case_details[2],
                'case_number': case_details[3],
                'submitted_on': case_details[5].strftime('%Y-%m-%d')
            }

        result = {
            'status': 'Success',
            'last_hearing': '2024-07-19 (Dummy)'
        }

    # Always regenerate new CAPTCHA for GET or failed POST
    session['captcha_num1'] = random.randint(1, 10)
    session['captcha_num2'] = random.randint(1, 10)

    cur.close()
    conn.close()
    return render_template('dashboard.html', courts=courts, result=result, case_details=case_details)

@app.route('/file-case', methods=['GET', 'POST'])
def file_case():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        court = request.form['court']
        case_type = request.form['case_type']
        case_number = request.form['case_number']
        filing_year = request.form['filing_year']
        submission_date = request.form['submission_date']
        proposal_hearing_date = request.form['proposal_hearing_date']
        parties = request.form['parties']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO case_queries (court_name, case_type, case_number, filing_year, submission_date, proposal_hearing_date, parties)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (court, case_type, case_number, filing_year, submission_date, proposal_hearing_date, parties))
        conn.commit()
        cur.close()
        conn.close()

        flash("✅ Case filed successfully.")
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT court_name FROM case_queries ORDER BY court_name ASC")
    courts = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template("file_case.html", courts=courts)

@app.route('/view-cases')
def view_cases():
    if 'user' not in session:
        return redirect(url_for('login'))

    page = int(request.args.get('page', 1))
    search = request.args.get('search', '')
    per_page = 5
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if search:
        cur.execute("""
            SELECT COUNT(*) FROM case_queries
            WHERE court_name ILIKE %s OR case_number ILIKE %s
        """, (f'%{search}%', f'%{search}%'))
        total = cur.fetchone()['count']

        cur.execute("""
            SELECT * FROM case_queries
            WHERE court_name ILIKE %s OR case_number ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (f'%{search}%', f'%{search}%', per_page, offset))
    else:
        cur.execute("SELECT COUNT(*) FROM case_queries")
        total = cur.fetchone()['count']

        cur.execute("""
            SELECT * FROM case_queries
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        'view_cases.html',
        rows=rows,
        page=page,
        total_pages=total_pages,
        search=search
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
