
import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify, flash, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pdfkit
import secrets, string as _string

# --- App & DB config ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
# DATABASE_URL (Render/PG) or SQLite fallback
db_url = os.environ.get('DATABASE_URL')
if db_url:
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    if db_url.startswith('postgresql') and 'sslmode=' not in db_url:
        db_url += ('&' if '?' in db_url else '?') + 'sslmode=require'
    SQLALCHEMY_DATABASE_URI = db_url
else:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'service.db')
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'schimba-aceasta-cheie')

# Uploads
ALLOWED_LOGO_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'logos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class Workshop(db.Model):
    __tablename__ = 'workshops'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    branding_color = db.Column(db.String(20), default='#2563eb')
    logo_path = db.Column(db.String(255))
    users = db.relationship('User', backref='workshop', lazy=True)
    mechanics = db.relationship('Mechanic', backref='workshop', lazy=True)
    fise = db.relationship('FisaDeLucru', backref='workshop', lazy=True)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' sau 'user'
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Mechanic(db.Model):
    __tablename__ = 'mechanics'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)

class ArticolLucrare(db.Model):
    __tablename__ = 'articole_lucrare'
    id = db.Column(db.Integer, primary_key=True)
    descriere = db.Column(db.String(200), nullable=False)
    cantitate = db.Column(db.Float, default=1.0)
    pret_unitar = db.Column(db.Integer, default=0)
    fisa_id = db.Column(db.Integer, db.ForeignKey('fise_de_lucru.id'), nullable=False)

class FisaDeLucru(db.Model):
    __tablename__ = 'fise_de_lucru'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    nr_inmatriculare = db.Column(db.String(10), nullable=False)
    tip_auto = db.Column(db.String(100), nullable=False)
    nume_mecanic = db.Column(db.String(100), nullable=False)
    descriere_generala = db.Column(db.Text)
    durata_ore = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='asteptare')  # asteptare, in lucru, finalizat
    vat_rate = db.Column(db.Integer, default=21)
    total_net = db.Column(db.Integer, default=0)
    vat_amount = db.Column(db.Integer, default=0)
    total_gross = db.Column(db.Integer, default=0)
    # public client access
    public_code = db.Column(db.String(16), unique=True)
    client_nume = db.Column(db.String(120))
    client_telefon = db.Column(db.String(40))
    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    articole_lista = db.relationship('ArticolLucrare', backref='fisa_de_lucru', lazy=True, cascade="all, delete-orphan")

# Utils
ALLOWED_STATUSES = {'asteptare','in lucru','finalizat'}

def status_label(s):
    return {'asteptare':'în așteptare','in lucru':'în lucru','finalizat':'finalizat'}.get(s,s)

def _wkhtmltopdf_config():
    candidates = [
        os.environ.get("WKHTMLTOPDF_PATH"),
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\ProgramData\chocolatey\bin\wkhtmltopdf.exe",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return pdfkit.configuration(wkhtmltopdf=p)
    return None

def _gen_public_code(n=8):
    alphabet = _string.ascii_uppercase + _string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

# Login loader
@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

# ---- PWA assets at root ----
@app.route('/manifest.webmanifest')
def manifest_webmanifest():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.webmanifest', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

# ---- Auth ----
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = (request.form.get('username') or '').strip()
        p = request.form.get('password') or ''
        user = User.query.filter_by(username=u).first()
        if user and user.check_password(p):
            login_user(user)
            return redirect(url_for('home'))
        flash('Nume de utilizator sau parolă greșite.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---- Home ----
@app.route('/')
@login_required
def home():
    return render_template('home.html', workshop_name=current_user.workshop.name if current_user.workshop else '-', user=current_user)

# ---- Formular fișă ----
@app.route('/formular', methods=['GET','POST'])
@login_required
def index():
    if request.method == 'POST':
        nr_inmatriculare = request.form.get('nr_inmatriculare','').strip().upper()
        tip_auto = request.form.get('tip_auto','').strip()
        nume_mecanic = request.form.get('nume_mecanic','').strip()
        descriere_generala = request.form.get('descriere_generala','')
        client_nume = request.form.get('client_nume','')
        client_telefon = request.form.get('client_telefon','')

        durata_ore = float(request.form.get('durata_ore','0') or 0)
        status = request.form.get('status','asteptare')
        vat_rate = int(request.form.get('vat_rate','21') or 21)
        total_net = int(request.form.get('total_net_ascuns','0') or 0)
        vat_amount = int(request.form.get('vat_amount_ascuns','0') or 0)
        total_gross = int(request.form.get('total_gross_ascuns','0') or 0)

        code = _gen_public_code()
        while FisaDeLucru.query.filter_by(public_code=code).first() is not None:
            code = _gen_public_code()

        f = FisaDeLucru(
            nr_inmatriculare=nr_inmatriculare, tip_auto=tip_auto,
            nume_mecanic=nume_mecanic, descriere_generala=descriere_generala,
            client_nume=client_nume or None, client_telefon=client_telefon or None,
            durata_ore=durata_ore, status=(status if status in ALLOWED_STATUSES else 'asteptare'),
            vat_rate=vat_rate, total_net=total_net, vat_amount=vat_amount, total_gross=total_gross,
            public_code=code, workshop_id=current_user.workshop_id, )
        db.session.add(f); db.session.commit()
        flash('Fișa a fost creată.', 'ok')
        return redirect(url_for('listare'))
    # GET
    mecs = Mechanic.query.filter_by(workshop_id=current_user.workshop_id).all()
    return render_template('index.html', mecanici=mecs, user=current_user)

# ---- Listare fișe ----
@app.route('/listare')
@login_required
def listare():
    fise = FisaDeLucru.query.filter_by(workshop_id=current_user.workshop_id).order_by(FisaDeLucru.id.desc()).all()
    return render_template('listare.html', fise=fise, status_label=status_label)

# ---- Mecanici ----
@app.route('/mecanici', methods=['GET','POST'])
@login_required
def gestioneaza_mecanici():
    if request.method == 'POST':
        nume = (request.form.get('nume_mecanic_nou') or '').strip()
        if nume:
            m = Mechanic(name=nume, workshop_id=current_user.workshop_id)
            db.session.add(m); db.session.commit()
            flash('Mecanic adăugat.', 'ok')
        return redirect(url_for('gestioneaza_mecanici'))
    mecs = Mechanic.query.filter_by(workshop_id=current_user.workshop_id).all()
    return render_template('mecanici.html', mecanici=mecs)

@app.route('/mecanici/<int:id>/delete', methods=['POST'])
@login_required
def sterge_mecanic(id):
    m = Mechanic.query.filter_by(id=id, workshop_id=current_user.workshop_id).first_or_404()
    db.session.delete(m); db.session.commit()
    flash('Mecanic șters.', 'ok')
    return redirect(url_for('gestioneaza_mecanici'))

# ---- PDF ----
@app.route('/pdf/<int:id>')
@login_required
def generare_pdf(id):
    fisa = FisaDeLucru.query.get_or_404(id)
    html_content = render_template('fisa_pdf.html', fisa=fisa, data=fisa.data.strftime('%d.%m.%Y %H:%M'), status_label=status_label)
    config = _wkhtmltopdf_config()
    try:
        options = {"page-size":"A4","margin-top":"8mm","margin-right":"8mm","margin-bottom":"10mm","margin-left":"8mm","encoding":"UTF-8"}
        pdf_bytes = pdfkit.from_string(html_content, False, configuration=config, options=options)
    except OSError:
        return ("wkhtmltopdf nu a fost găsit. Instalează-l și/sau setează variabila WKHTMLTOPDF_PATH.", 500)
    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename=Fisa_{fisa.nr_inmatriculare}_{fisa.id}.pdf'
    return resp

# ---- Dashboard ----
@app.route('/dashboard')
@login_required
def dashboard():
    statuses = ['asteptare','in lucru','finalizat']
    mecs = Mechanic.query.filter_by(workshop_id=current_user.workshop_id).all()
    return render_template('dashboard.html', statuses=statuses, mecanici=mecs, status_label=status_label)

@app.route('/api/dashboard_data')
@login_required
def api_dashboard_data():
    # Filters
    mechanics = (request.args.get('mechanics') or '').split(',') if request.args.get('mechanics') else []
    statuses = (request.args.get('status') or '').split(',') if request.args.get('status') else []
    start = request.args.get('start')
    end = request.args.get('end')

    q = FisaDeLucru.query.filter_by(workshop_id=current_user.workshop_id)
    if mechanics:
        q = q.filter(FisaDeLucru.nume_mecanic.in_(mechanics))
    if statuses:
        q = q.filter(FisaDeLucru.status.in_(statuses))
    if start:
        try:
            d = datetime.strptime(start, "%Y-%m-%d"); q = q.filter(FisaDeLucru.data >= d)
        except: pass
    if end:
        try:
            d2 = datetime.strptime(end, "%Y-%m-%d"); q = q.filter(FisaDeLucru.data < d2.replace(hour=23, minute=59, second=59))
        except: pass

    rows = q.all()
    kpis = {
        'total_revenue_gross': sum(r.total_gross or r.total_net or 0 for r in rows),
        'total_revenue_net': sum(r.total_net or 0 for r in rows),
        'total_vat': sum(r.vat_amount or 0 for r in rows),
        'job_count': len(rows)
    }
    # Aggregations
    by_month = {}
    by_mech = {}
    status_dist = {}
    daily = {}
    for r in rows:
        mkey = r.data.strftime("%Y-%m")
        by_month[mkey] = by_month.get(mkey, 0) + (r.total_gross or 0)
        by_mech[r.nume_mecanic] = by_mech.get(r.nume_mecanic, 0) + (r.total_gross or 0)
        status_dist[r.status] = status_dist.get(r.status, 0) + 1
        dkey = r.data.strftime("%Y-%m-%d")
        daily[dkey] = daily.get(dkey, 0) + 1

    return jsonify({
        'kpis': kpis,
        'revenue_by_month': [{'month': k, 'value': v} for k, v in sorted(by_month.items())],
        'revenue_by_mechanic': [{'mechanic': k, 'value': v} for k, v in sorted(by_mech.items())],
        'status_distribution': [{'label': status_label(k), 'count': v} for k, v in status_dist.items()],
        'daily_jobs': [{'date': k, 'count': v} for k, v in sorted(daily.items())]
    })

# ---- Admin: workshops + branding ----
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return fn(*a, **kw)
    return wrapper

@app.route('/admin')
@login_required
@admin_required
def admin_home():
    wcount = Workshop.query.count()
    ucount = User.query.count()
    return render_template('admin/home.html', wcount=wcount, ucount=ucount)

@app.route('/admin/workshops')
@login_required
@admin_required
def admin_workshops():
    w = Workshop.query.all()
    return render_template('admin/workshops.html', workshops=w)

@app.route('/admin/workshops/create', methods=['POST'])
@login_required
@admin_required
def admin_create_workshop():
    name = (request.form.get('name') or '').strip()
    if name:
        ws = Workshop(name=name)
        db.session.add(ws); db.session.commit()
        flash('Atelier creat.', 'ok')
    return redirect(url_for('admin_workshops'))

@app.route('/admin/branding/<int:wid>', methods=['GET','POST'])
@login_required
@admin_required
def admin_branding(wid):
    ws = Workshop.query.get_or_404(wid)
    if request.method == 'POST':
        color = request.form.get('branding_color', ws.branding_color).strip() or '#2563eb'
        ws.branding_color = color
        file = request.files.get('logo')
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ALLOWED_LOGO_EXT:
                fname = secure_filename(f'ws_{ws.id}{ext}')
                save_path = os.path.join(UPLOAD_FOLDER, fname)
                file.save(save_path)
                ws.logo_path = f'logos/{fname}'
            else:
                flash('Format invalid. Folosește PNG/JPG/SVG/WebP.', 'error')
                return redirect(url_for('admin_branding', wid=ws.id))
        db.session.commit()
        flash('Branding actualizat.', 'ok')
        return redirect(url_for('admin_branding', wid=ws.id))
    return render_template('admin/branding.html', ws=ws)

# ---- Client public ----
@app.route('/client', methods=['GET','POST'])
def client_lookup():
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().upper()
        if not code:
            flash('Introdu codul de urmărire.', 'error')
            return redirect(url_for('client_lookup'))
        f = FisaDeLucru.query.filter_by(public_code=code).first()
        if not f:
            flash('Cod invalid sau fișa nu există.', 'error')
            return redirect(url_for('client_lookup'))
        return redirect(url_for('client_view', code=code))
    return render_template('client_lookup.html')

@app.route('/client/<code>')
def client_view(code):
    code = (code or '').strip().upper()
    f = FisaDeLucru.query.filter_by(public_code=code).first_or_404()
    return render_template('client_status.html', f=f, status_label=status_label)

@app.route('/api/client/<code>')
def client_api(code):
    code = (code or '').strip().upper()
    f = FisaDeLucru.query.filter_by(public_code=code).first_or_404()
    items = [{'descriere': a.descriere, 'cantitate': a.cantitate, 'pret_unitar': a.pret_unitar,
              'total': int((a.cantitate or 0) * (a.pret_unitar or 0))} for a in f.articole_lista]
    return jsonify({
        'code': f.public_code,
        'status': f.status, 'status_label': status_label(f.status),
        'nr_inmatriculare': f.nr_inmatriculare, 'tip_auto': f.tip_auto, 'nume_mecanic': f.nume_mecanic,
        'descriere_generala': f.descriere_generala,
        'total_net': f.total_net, 'vat_amount': f.vat_amount, 'total_gross': f.total_gross,
        'data': f.data.isoformat(), 'items': items
    })

# ---- Init demo data ----
@app.before_first_request
# --- RÉGI (törlendő) ---
# @app.before_first_request
# def init_db():
#     db.create_all()
#     ...

# --- ÚJ (használd ezt) ---
def init_db():
    with app.app_context():
        db.create_all()
        ws = Workshop.query.filter_by(name='Atelier Demo').first()
        if not ws:
            ws = Workshop(name='Atelier Demo', branding_color='#2563eb')
            db.session.add(ws); db.session.commit()

        user = User.query.filter_by(username='demo').first()
        if not user:
            user = User(username='demo', role='admin', workshop_id=ws.id)
            user.set_password('demo')
            db.session.add(user); db.session.commit()

        if not Mechanic.query.filter_by(workshop_id=ws.id).first():
            db.session.add(Mechanic(name='Mecanic Demo', workshop_id=ws.id)); db.session.commit()

# Flask 3.x: dipatcher replace for before_first_request
# Egyértelmű, idempotens inicializálás induláskor
if os.environ.get("INIT_DB_ON_STARTUP", "1") == "1":
    init_db()


# ---- Run ----
if __name__ == '__main__':
    app.run(debug=True)
