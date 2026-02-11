from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import sqlite3
import random
import datetime
import qrcode
import io

app = Flask(__name__)
app.secret_key = "cle_secrete_pour_le_projet"

# --- GESTION BASE DE DONNEES (SQL) ---
def init_db():
    conn = sqlite3.connect('ecole.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS etudiants (
                    id_unique INTEGER PRIMARY KEY,
                    nom TEXT NOT NULL,
                    prenom TEXT NOT NULL,
                    age INTEGER,
                    heure_arrivee TEXT
                )''')
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
    identifiant = request.form['identifiant']
    if identifiant == "admin":
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Identifiant incorrect", "danger")
        return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    conn = get_db_connection()
    etudiants = conn.execute('SELECT * FROM etudiants').fetchall()
    conn.close()
    return render_template('admin.html', etudiants=etudiants)

@app.route('/ajouter_etudiant', methods=['POST'])
def ajouter_etudiant():
    nom = request.form['nom']
    prenom = request.form['prenom']
    age = request.form['age']
    id_unique = generate_student_id()
    
    conn = get_db_connection()
    while conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (id_unique,)).fetchone():
        id_unique = generate_student_id()
        
    conn.execute('INSERT INTO etudiants (id_unique, nom, prenom, age, heure_arrivee) VALUES (?, ?, ?, ?, ?)',
                 (id_unique, nom, prenom, age, "Non scanné"))
    conn.commit()
    conn.close()
    flash(f"Étudiant ajouté avec succès ! ID: {id_unique}", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/supprimer_etudiant/<int:id_unique>')
def supprimer_etudiant(id_unique):
    conn = get_db_connection()
    conn.execute('DELETE FROM etudiants WHERE id_unique = ?', (id_unique,))
    conn.commit()
    conn.close()
    flash("Étudiant supprimé.", "warning")
    return redirect(url_for('admin_dashboard'))

@app.route('/generate_qr/<int:id_unique>')
def generate_qr(id_unique):
    img = qrcode.make(str(id_unique))
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# -- Espace Surveillant --
@app.route('/surveillant_login', methods=['POST'])
def surveillant_login():
    identifiant = request.form['identifiant']
    password = request.form['password']
    if identifiant == "surv" and password == "1234":
        return redirect(url_for('scan_page'))
    else:
        flash("Identifiants incorrects", "danger")
        return redirect(url_for('index'))

@app.route('/scan')
def scan_page():
    return render_template('scan.html', etudiant=None)

# Ancienne méthode (formulaire + douchette)
@app.route('/process_scan', methods=['POST'])
def process_scan():
    qr_data = request.form.get('qr_code')
    
    if not qr_data:
        return render_template('scan.html', etudiant=None, error="Aucun code fourni.")
    
    conn = get_db_connection()
    etudiant = conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (qr_data,)).fetchone()
    
    if etudiant:
        nouvelle_heure = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('UPDATE etudiants SET heure_arrivee = ? WHERE id_unique = ?', (nouvelle_heure, qr_data))
        conn.commit()
        etudiant_maj = conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (qr_data,)).fetchone()
        conn.close()
        return render_template('scan.html', etudiant=etudiant_maj, message="Arrivée enregistrée !")
    else:
        conn.close()
        return render_template('scan.html', etudiant=None, error="ID inconnu.")

# Nouvelle méthode (scan webcam via JavaScript)
@app.route('/valider_scan', methods=['POST'])
def valider_scan():
    data = request.get_json()
    student_id = data.get('id')
    
    if not student_id:
        return jsonify({"success": False, "message": "ID manquant"}), 400
    
    conn = get_db_connection()
    etudiant = conn.execute('SELECT * FROM etudiants WHERE id_unique = ?', (student_id,)).fetchone()
    
    if not etudiant:
        conn.close()
        return jsonify({"success": False, "message": "Étudiant non trouvé"}), 404
    
    nouvelle_heure = datetime.datetime.now().strftime("%H:%M:%S")
    conn.execute('UPDATE etudiants SET heure_arrivee = ? WHERE id_unique = ?', 
                 (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), student_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "heure": nouvelle_heure
    })
if __name__ == '__main__':
    app.run(debug=True, port=5001)