# Gunakan image Python yang ringan
FROM python:3.11-slim

# Set environment variables untuk Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set direktori kerja di dalam container
WORKDIR /app

# (Wajib untuk database MySQL) Install dependensi sistem 
# yang dibutuhkan untuk menginstal psycopg2 / pymysql dsb.
RUN apt-get update && apt-get install -y \
    gcc \
    libssl-dev \
    libffi-dev \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Salin requirements dan install library Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode aplikasi (app.py, templates, static, dll.)
COPY . .

# Buat folder untuk upload (untuk izin akses menulis)
RUN mkdir -p static/uploads

# Expose port Flask
EXPOSE 5000

# Perintah menjalankan aplikasi (CMD terakhir harus jalan)
# Untuk production, disarankan menggunakan Gunicorn, tapi python app.py sudah cukup.
CMD ["python", "app.py"]