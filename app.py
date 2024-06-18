from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from pymongo import MongoClient, DESCENDING
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from os.path import join, dirname
from dotenv import load_dotenv
import hashlib
import jwt
import os

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
pendaftar_collection = db['pendaftar']

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user = pendaftar_collection.find_one({"email": email})

        if user and user['password'] == hashed_password:
            token = jwt.encode({'email': email, 'namaSiswa': user['namaSiswa'], 'user_id': str(user['_id']), 'exp': datetime.utcnow() + timedelta(minutes=30)},
                               app.secret_key, algorithm="HS256")
            resp = make_response(redirect(url_for('home_user')))
            resp.set_cookie('token', token)
            flash('Login Berhasil', 'success')
            return resp
        else:
            message = 'Email atau kata sandi salah'
            return jsonify({'message': message}), 401  
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        namaSiswa = request.form['namaSiswa']
        email = request.form['email']
        password = request.form['password']

        # Validasi password minimal 8 karakter, huruf besar, dan angka
        if not (len(password) >= 8 and any(c.isupper() for c in password) and any(c.isdigit() for c in password)):
            return jsonify({'message': 'Password harus terdiri dari minimal 8 karakter, huruf besar, dan angka.'}), 400

        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        user = pendaftar_collection.find_one({"email": email})

        if user:
            return jsonify({'message': 'Email sudah terdaftar'}), 400

        pendaftar_collection.insert_one({
            'namaSiswa': namaSiswa,
            'email': email,
            'password': hashed_password,
            'pendaftaran': [] 
        })

        token = jwt.encode({'email': email, 'namaSiswa': namaSiswa, 'exp': datetime.utcnow() + timedelta(minutes=30)},
                           app.secret_key, algorithm="HS256")

        return jsonify({'message': 'Pendaftaran akun berhasil'}), 200

    return render_template('register.html')

@app.route('/home_user')
def home_user():
    token = request.cookies.get('token')
    if not token:
        return redirect(url_for('login'))

    try:
        data = jwt.decode(token, app.secret_key, algorithms=["HS256"])
        user = data['namaSiswa']
        return render_template('home_user.html', user=user)
    except jwt.ExpiredSignatureError:
        return redirect(url_for('login'))
    except jwt.InvalidTokenError:
        return redirect(url_for('login'))

@app.route('/pendaftaran_siswa')
def pendaftaran_siswa():
    token = request.cookies.get('token')
    if not token:
        return redirect(url_for('login'))

    try:
        data = jwt.decode(token, app.secret_key, algorithms=["HS256"])
        user_id = ObjectId(data['user_id'])

        # Periksa apakah pengguna telah mengirimkan formulir pendaftaran sebelumnya
        user = pendaftar_collection.find_one({'_id': user_id})
        if user and 'pendaftaran' in user and user['pendaftaran']:
            user_has_submitted = True
        else:
            user_has_submitted = False

        return render_template('pendaftaran_siswa.html', user=user['namaSiswa'], user_has_submitted=user_has_submitted)
    except jwt.ExpiredSignatureError:
        return redirect(url_for('login'))
    except jwt.InvalidTokenError:
        return redirect(url_for('login'))

@app.route('/submit', methods=['POST'])
def submit():
    token = request.cookies.get('token')
    if not token:
        return redirect(url_for('login'))

    try:
        data = jwt.decode(token, app.secret_key, algorithms=["HS256"])
        user_id = ObjectId(data['user_id'])

        # Mengambil data dari form
        nama = request.form.get('nama')
        tanggal_lahir = request.form.get('tanggalLahir')
        asal_provinsi = request.form.get('asal_provinsi')
        nama_ayah = request.form.get('nama_ayah')
        nama_ibu = request.form.get('nama_ibu')
        nik = request.form.get('nik')
        jenis_kelamin = request.form.get('jenis_kelamin')
        file_photo = request.files['filePhoto']
        file_dokumen = request.files['fileDokumen']

        # Validasi NIK hanya angka bukan variabel atau karakter
        if not nik.isdigit():
            return "NIK harus berupa angka.", 400

        # Menyimpan file upload ke server
        photo_filename = file_photo.filename
        dokumen_filename = file_dokumen.filename
        file_photo.save(f'static/{photo_filename}')
        file_dokumen.save(f'static/{dokumen_filename}')

        # format waktu
        timestamp = datetime.now().strftime("%A, %d %B %Y")

        # Membuat dokumen pendaftaran untuk disimpan ke MongoDB
        pendaftaran = {
            'nama': nama,
            'tanggal_lahir': tanggal_lahir,
            'asal_provinsi': asal_provinsi,
            'nama_ayah': nama_ayah,
            'nama_ibu': nama_ibu,
            'nik': nik,
            'jenis_kelamin': jenis_kelamin,
            'file_photo': photo_filename,
            'file_dokumen': dokumen_filename,
            'status': 'Menunggu Konfirmasi',
            'timestamp': timestamp
        }

        # Menambahkan data pendaftaran ke dokumen pengguna yang sudah ada
        pendaftar_collection.update_one({'_id': user_id}, {'$push': {'pendaftaran': pendaftaran}})

        return redirect(url_for('riwayat_pendaftaran'))
    except jwt.ExpiredSignatureError:
        return redirect(url_for('login'))
    except jwt.InvalidTokenError:
        return redirect(url_for('login'))

@app.route('/riwayat_pendaftaran')
def riwayat_pendaftaran():
    token = request.cookies.get('token')
    if not token:
        return redirect(url_for('login'))
    try:
        data = jwt.decode(token, app.secret_key, algorithms=["HS256"])
        user_id = ObjectId(data['user_id'])
        user = pendaftar_collection.find_one({'_id': user_id}, {'pendaftaran': 1})

        if user and 'pendaftaran' in user:
            pendaftar_list = user['pendaftaran']
        else:
            pendaftar_list = []

        return render_template('riwayat_pendaftaran.html', pendaftar_list=pendaftar_list, user=user)
    except jwt.ExpiredSignatureError:
        return redirect(url_for('login'))
    except jwt.InvalidTokenError:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('token', '', expires=0)
    flash('Logout Berhasil', 'success')
    return resp

if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=True)
