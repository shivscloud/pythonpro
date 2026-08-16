from flask import Flask, render_template, request, redirect, session, url_for, send_file, make_response, flash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import os
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import timedelta
from dotenv import load_dotenv


# Load environment variables from .env for local development
load_dotenv()


# ============================================================
# Flask Application Configuration
# ============================================================

app = Flask(__name__)

# NEVER hardcode secrets in application code.
# The value must be supplied through the environment.
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY environment variable is required"
    )

app.permanent_session_lifetime = timedelta(minutes=30)

# ============================================================
# Database Configuration
# ============================================================
def get_database_config():
    """
    Build PostgreSQL configuration from environment variables.

    Preferred:
        DATABASE_URL

    Alternative:
        DATABASE_HOST
        DATABASE_NAME
        DATABASE_USER
        DATABASE_PASSWORD
        DATABASE_PORT
        DATABASE_SSLMODE
    """

    database_url = os.getenv("DATABASE_URL")

    # --------------------------------------------------------
    # Option 1: DATABASE_URL
    # --------------------------------------------------------

    if database_url:
        return {
            "dsn": database_url,
            "sslmode": os.getenv(
                "DATABASE_SSLMODE",
                "require"
            )
        }



    required_variables = [
        "DATABASE_HOST",
        "DATABASE_NAME",
        "DATABASE_USER",
        "DATABASE_PASSWORD"
    ]

    missing_variables = [
        variable
        for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing_variables:
        raise RuntimeError(
            "Missing required database environment variables: "
            + ", ".join(missing_variables)
        )

    return {
        "host": os.getenv("DATABASE_HOST"),
        "database": os.getenv("DATABASE_NAME"),
        "user": os.getenv("DATABASE_USER"),
        "password": os.getenv("DATABASE_PASSWORD"),
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "sslmode": os.getenv(
            "DATABASE_SSLMODE",
            "require"
        )
    }


def get_db_connection():
    """
    Create a PostgreSQL connection using runtime configuration.

    No database credentials are stored in source code.
    """
    config = get_database_config()
    # DATABASE_URL mode
    if "dsn" in config:
        return psycopg2.connect(
            config["dsn"],
            sslmode=config["sslmode"]
        )
    # Individual environment variables mode
    return psycopg2.connect(**config)


# ============================================================
# Database Initialization
# ============================================================

def init_db():
    """
    Initialize required database tables.

    This function is intentionally NOT executed automatically
    when Gunicorn starts the Flask application.

    It can be executed separately during initial deployment
    or as a Kubernetes Job later.
    """

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS case_queries (
                id SERIAL PRIMARY KEY,
                court_name VARCHAR(255) NOT NULL,
                case_type VARCHAR(255) NOT NULL,
                case_number VARCHAR(255) NOT NULL,
                filing_year INT,
                submission_date DATE,
                proposal_hearing_date DATE,
                parties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()

# ============================================================
# Kubernetes Health Check
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    """
    Liveness endpoint.

    This endpoint intentionally does NOT check PostgreSQL.

    Kubernetes uses this endpoint to determine whether
    the Flask application process is alive.
    """

    return {
        "status": "healthy",
        "application": "healthy"
    }, 200


# ============================================================
# Kubernetes Readiness Check
# ============================================================

@app.route("/ready", methods=["GET"])
def readiness():
    """
    Readiness endpoint.

    Checks whether the Flask application can communicate
    with PostgreSQL.

    PostgreSQL is tested using a lightweight:

        SELECT 1

    If PostgreSQL is unavailable, HTTP 503 is returned.
    """

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT 1")
        result = cur.fetchone()

        if result and result[0] == 1:
            return {
                "status": "ready",
                "application": "healthy",
                "database": "healthy"
            }, 200

        return {
            "status": "not_ready",
            "application": "healthy",
            "database": "unhealthy"
        }, 503

    except Exception:
        # Do not expose database connection details
        # to the client.
        return {
            "status": "not_ready",
            "application": "healthy",
            "database": "unhealthy"
        }, 503

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# Home
# ============================================================

@app.route("/")
def home():
    return redirect(url_for("login"))


# ============================================================
# Login
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form["username"]
        session["user"] = username
        return redirect(url_for("dashboard"))
    return render_template("login.html")


# ============================================================
# Download Case PDF
# ============================================================

@app.route("/download_pdf")
def download_pdf():
    if "case_details" not in session:
        flash("No case details to download.")
        return redirect(url_for("dashboard"))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=letter
    )

    pdf.setFont(
        "Helvetica",
        12
    )

    pdf.drawString(
        100,
        750,
        "Case Details Report"
    )

    pdf.drawString(
        100,
        730,
        f"Court Name: {session['case_details'][1]}"
    )

    pdf.drawString(
        100,
        710,
        f"Case Type: {session['case_details'][2]}"
    )

    pdf.drawString(
        100,
        690,
        f"Case Number: {session['case_details'][3]}"
    )

    pdf.drawString(
        100,
        670,
        f"Submitted On: {session['case_details'][5]}"
    )

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="case_details.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# Dashboard
# ============================================================

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT court_name
            FROM case_queries
            ORDER BY court_name ASC
        """)

        courts = [
            row[0]
            for row in cur.fetchall()
        ]

        result = None
        case_details = None

        # ----------------------------------------------------
        # POST
        # ----------------------------------------------------

        if request.method == "POST":
            try:

                user_answer = int(
                    request.form["captcha_answer"]
                )

            except ValueError:

                flash(
                    "❌ Invalid CAPTCHA input."
                )

                return redirect(
                    url_for("dashboard")
                )

            correct_answer = (
                session.get("captcha_num1", 0)
                +
                session.get("captcha_num2", 0)
            )

            if user_answer != correct_answer:

                flash(
                    "❌ CAPTCHA failed. Try again."
                )

                return redirect(
                    url_for("dashboard")
                )

            court = request.form["court"]
            case_type = request.form["case_type"]
            case_number = request.form["case_number"]

            cur.execute("""
                SELECT *
                FROM case_queries
                WHERE court_name = %s
                  AND case_type = %s
                  AND case_number = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (
                court,
                case_type,
                case_number
            ))

            case_details = cur.fetchone()

            if case_details:

                session["latest_case"] = {
                    "court": case_details[1],
                    "case_type": case_details[2],
                    "case_number": case_details[3],
                    "submitted_on": (
                        case_details[5].strftime("%Y-%m-%d")
                    )
                }

            result = {
                "status": "Success",
                "last_hearing": "2024-07-19 (Dummy)"
            }

        # ----------------------------------------------------
        # Generate CAPTCHA
        # ----------------------------------------------------

        session["captcha_num1"] = random.randint(
            1,
            10
        )

        session["captcha_num2"] = random.randint(
            1,
            10
        )

        return render_template(
            "dashboard.html",
            courts=courts,
            result=result,
            case_details=case_details
        )

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# File Case
# ============================================================

@app.route("/file-case", methods=["GET", "POST"])
def file_case():

    if "user" not in session:
        return redirect(url_for("login"))

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        court = request.form["court"]
        case_type = request.form["case_type"]
        case_number = request.form["case_number"]
        filing_year = request.form["filing_year"]
        submission_date = request.form["submission_date"]
        proposal_hearing_date = request.form[
            "proposal_hearing_date"
        ]
        parties = request.form["parties"]

        conn = None
        cur = None

        try:

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO case_queries (
                    court_name,
                    case_type,
                    case_number,
                    filing_year,
                    submission_date,
                    proposal_hearing_date,
                    parties
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                court,
                case_type,
                case_number,
                filing_year,
                submission_date,
                proposal_hearing_date,
                parties
            ))

            conn.commit()

        finally:

            if cur:
                cur.close()

            if conn:
                conn.close()

        flash(
            "✅ Case filed successfully."
        )

        return redirect(
            url_for("dashboard")
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT court_name
            FROM case_queries
            ORDER BY court_name ASC
        """)

        courts = [
            row[0]
            for row in cur.fetchall()
        ]

        return render_template(
            "file_case.html",
            courts=courts
        )

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# View Cases
# ============================================================

@app.route("/view-cases")
def view_cases():

    if "user" not in session:
        return redirect(url_for("login"))

    page = int(
        request.args.get(
            "page",
            1
        )
    )

    search = request.args.get(
        "search",
        ""
    )

    per_page = 5

    offset = (
        page - 1
    ) * per_page

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        # ----------------------------------------------------
        # Search
        # ----------------------------------------------------

        if search:

            cur.execute("""
                SELECT COUNT(*)
                FROM case_queries
                WHERE court_name ILIKE %s
                   OR case_number ILIKE %s
            """, (
                f"%{search}%",
                f"%{search}%"
            ))

            total = cur.fetchone()["count"]

            cur.execute("""
                SELECT *
                FROM case_queries
                WHERE court_name ILIKE %s
                   OR case_number ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                OFFSET %s
            """, (
                f"%{search}%",
                f"%{search}%",
                per_page,
                offset
            ))

        # ----------------------------------------------------
        # No Search
        # ----------------------------------------------------

        else:

            cur.execute("""
                SELECT COUNT(*)
                FROM case_queries
            """)

            total = cur.fetchone()["count"]

            cur.execute("""
                SELECT *
                FROM case_queries
                ORDER BY created_at DESC
                LIMIT %s
                OFFSET %s
            """, (
                per_page,
                offset
            ))

        rows = cur.fetchall()

        total_pages = (
            total + per_page - 1
        ) // per_page

        return render_template(
            "view_cases.html",
            rows=rows,
            page=page,
            total_pages=total_pages,
            search=search
        )

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# Logout
# ============================================================

@app.route("/logout")
def logout():

    session.pop(
        "user",
        None
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# Local Development
# ============================================================

if __name__ == "__main__":

    # Database initialization is performed only when
    # running this file directly.
    #
    # Gunicorn/Kubernetes will NOT execute init_db()
    # automatically.
    #
    # Later we can move database initialization to a
    # dedicated migration/Kubernetes Job.

    init_db()

    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )