from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
import sqlite3
import random
import datetime
import qrcode
import io
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)

# Configuration upload
UPLOAD_FOLDER = 'static/photos_etudiants'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024  # limite 4 Mo

# Crée le dossier s'il n'existe pas
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# we rely on the built-in session support, the secret key should be unique
app.secret_key = os.environ.get('FLASK_SECRET', 'cle_secrete_pour_le_projet')

# helper decorators

def login_required(role):
    """Decorator factory for simple session-based auth.

    ``role`` may be 'admin' or 'surv'.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if role == 'admin' and not session.get('admin_logged_in'):
                flash("Veuillez vous connecter comme administrateur.", "warning")
                return redirect(url_for('index'))
            if role == 'surv' and not session.get('surv_logged_in'):
                flash("Veuillez vous connecter comme surveillant.", "warning")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- GESTION BASE DE DONNEES (SQL) ---
def init_db():
    conn = sqlite3.connect('ecole.db')
    c = conn.cursor()
    # création de la table si elle n'existe pas encore
    c.execute('''CREATE TABLE IF NOT EXISTS etudiants (
                    id_unique INTEGER PRIMARY KEY,
                    nom TEXT NOT NULL,
                    prenom TEXT NOT NULL,
                    age INTEGER,
                    heure_arrivee TEXT,
                    photo TEXT DEFAULT NULL
                )''')
    # en cas de mise à jour depuis une ancienne version, s'assurer que
    # la colonne `photo` est bien présente (SQLite ne modifie pas la
    # structure d'une table existante avec IF NOT EXISTS).
    c.execute("PRAGMA table_info(etudiants)")
    cols = [row[1] for row in c.fetchall()]
    if 'photo' not in cols:
        c.execute("ALTER TABLE etudiants ADD COLUMN photo TEXT DEFAULT NULL")
    conn.commit()
    conn.close()

# Initialiser la DB au démarrage
init_db()

# --- FONCTIONS UTILIT Ascenseurs ---
def generate_student_id():
    """Génère un ID unique à 4 chiffres"""
    return random.randint(1000, 9999)

def get_db_connection():
    conn = sqlite3.connect('ecole.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- ROUTES (BACKEND) ---

@app.route('/')
def index():
    return render_template('index.html')

# -- Espace Administrateur --
@app.route('/admin_login', methods=['POST'])
def admin_login():
    identifiant = request.form.get('identifiant', '').strip()
    password = request.form.get('password', '').strip()

    # default credentials are hardcoded for the demo; replace with a proper
    # user system in a real application.
    if identifiant == "admin" and password == "admin123":
        session.clear()
        session['admin_logged_in'] = True
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Identifiant ou mot de passe incorrect.", "danger")
        return redirect(url_for('index'))

@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    etudiants = conn.execute('SELECT * FROM etudiants').fetchall()
    conn.close()
    return render_template('admin.html', etudiants=etudiants)

@app.route('/ajouter_etudiant', methods=['POST'])
@login_required('admin')
def ajouter_etudiant():
    nom = request.form.get('nom', '').strip()
    prenom = request.form.get('prenom', '').strip()
    age_raw = request.form.get('age', '').strip()
    try:
        age = int(age_raw)
    except (ValueError, TypeError):
        age = None
    id_unique = generate_student_id()
    photo_filename = None

    # garantie d'un ID unique dans la table
    conn = get_db_connection()
    while conn.execute('SELECT 1 FROM etudiants WHERE id_unique = ?', (id_unique,)).fetchone():
        id_unique = generate_student_id()

    # gestion du fichier photo si fourni
    file = request.files.get('photo')
    if file and file.filename:
        if allowed_file(file.filename):
            fname = secure_filename(file.filename)
            # préfixer par l'ID pour éviter collisions
            fname = f"{id_unique}_{fname}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            file.save(save_path)
            photo_filename = fname
        else:
            conn.close()
            flash("Format de photo non autorisé.", "danger")
            return redirect(url_for('admin_dashboard'))

    conn.execute(
        'INSERT INTO etudiants (id_unique, nom, prenom, age, heure_arrivee, photo) VALUES (?, ?, ?, ?, ?, ?)',
        (id_unique, nom, prenom, age, "Non scanné", photo_filename)
    )
    conn.commit()
    conn.close()
    flash(f"Étudiant ajouté avec succès ! ID : {id_unique}", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/supprimer_etudiant/<int:id_unique>')
@login_required('admin')
def supprimer_etudiant(id_unique):
    conn = get_db_connection()
    etu = conn.execute('SELECT photo FROM etudiants WHERE id_unique = ?', (id_unique,)).fetchone()
    if etu and etu['photo']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], etu['photo']))
        except OSError:
            pass  # fichier peut déjà avoir été supprimé
    conn.execute('DELETE FROM etudiants WHERE id_unique = ?', (id_unique,))
    conn.commit()
    conn.close()
    flash("Étudiant supprimé.", "warning")
    return redirect(url_for('admin_dashboard'))

@app.route('/generate_qr/<int:id_unique>')
@login_required('admin')
def generate_qr(id_unique):
    img = qrcode.make(str(id_unique))
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# -- Espace Surveillant --
@app.route('/surveillant_login', methods=['POST'])
def surveillant_login():
    identifiant = request.form.get('identifiant', '').strip()
    password = request.form.get('password', '').strip()
    if identifiant == "surv" and password == "1234":
        session.clear()
        session['surv_logged_in'] = True
        return redirect(url_for('scan_page'))
    else:
        flash("Identifiants incorrects", "danger")
        return redirect(url_for('index'))

@app.route('/scan')
@login_required('surv')
def scan_page():
    # la page elle-même est rendue vide ; les résultats de scan sont
    # affichés dynamiquement via JavaScript.
    return render_template('scan.html')

# la méthode plus ancienne n'est plus utilisée. le formulaire est
# géré côté client et fait appel à `/valider_scan` via AJAX.

# Nouvelle méthode (scan webcam via JavaScript) → MODIFIÉE
@app.route('/valider_scan', methods=['POST'])
@login_required('surv')
def valider_scan():
    # attend du JSON {id: "1234"}
    data = request.get_json(silent=True)
    student_id = None
    if data:
        student_id = data.get('id')
    else:
        # fallback lorsque l'appel n'est pas en JSON (non utilisé actuellement)
        student_id = request.form.get('qr_code')

    student_id = str(student_id).strip() if student_id else ''

    if not student_id:
        return jsonify(success=False, error="ID manquant"), 400

    conn = get_db_connection()
    etudiant = conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (student_id,)).fetchone()

    if not etudiant:
        conn.close()
        return jsonify(success=False, error="Étudiant non trouvé"), 404

    maintenant = datetime.datetime.now()
    heure_complete = maintenant.strftime("%Y-%m-%d %H:%M:%S")

    conn.execute('UPDATE etudiants SET heure_arrivee = ? WHERE id_unique = ?', 
                 (heure_complete, student_id))
    conn.commit()

    etudiant_maj = conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (student_id,)).fetchone()
    conn.close()

    # sqlite3.Row est dict-like
    return jsonify(success=True, student=dict(etudiant_maj))


@app.route('/logout')
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5001) 
