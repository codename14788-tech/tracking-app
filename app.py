import os
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template_string, request, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Sambungan ke Supabase menggunakan Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Zon waktu Malaysia (UTC+8)
MY_TZ = timezone(timedelta(hours=8))

# 1. Antaramuka untuk Rider / Pelanggan
HTML_LIVE_TRACK = """
<!DOCTYPE html>
<html lang="ms">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Tracking #{{ order_id }}</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 30px 15px; background: #f4f6f9; }
        .card { max-width: 420px; margin: auto; background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin-top: 10px; font-weight: bold; }
        .btn-start { background-color: #007bff; color: white; }
        .btn-stop { background-color: #dc3545; color: white; display: none; }
        .status-box { margin-top: 20px; padding: 12px; background: #e9ecef; border-radius: 6px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Penghantaran #{{ order_id }}</h2>
        <p>Tekan butang di bawah untuk berkongsi lokasi secara langsung (Live).</p>
        <button id="btnStart" class="btn-start" onclick="mulaTracking()">Mula Kongsi Lokasi</button>
        <button id="btnStop" class="btn-stop" onclick="hentiTracking()">Hentikan Perkongsian</button>
        <div class="status-box" id="status">Status: Menunggu arahan...</div>
    </div>

    <script>
        let watchId = null;
        function mulaTracking() {
            const status = document.getElementById("status");
            if (!navigator.geolocation) {
                status.innerText = "Pelayar tidak menyokong GPS.";
                return;
            }
            document.getElementById("btnStart").style.display = "none";
            document.getElementById("btnStop").style.display = "block";
            status.innerText = "Menghubungkan ke satelit GPS...";

            watchId = navigator.geolocation.watchPosition(
                (pos) => {
                    fetch('/api/update-lokasi', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            order_id: "{{ order_id }}",
                            lat: pos.coords.latitude,
                            lon: pos.coords.longitude,
                            accuracy: pos.coords.accuracy
                        })
                    })
                    .then(res => res.json())
                    .then(() => {
                        const masa = new Date().toLocaleTimeString();
                        status.innerHTML = `<strong>Aktif (Live)</strong><br>Kemaskini: ${masa}<br>Ketepatan: ±${Math.round(pos.coords.accuracy)}m`;
                    });
                },
                () => { status.innerText = "Akses lokasi ditolak atau isyarat GPS lemah."; },
                { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
            );
        }

        function hentiTracking() {
            if (watchId !== null) {
                navigator.geolocation.clearWatch(watchId);
                watchId = null;
            }
            document.getElementById("btnStart").style.display = "block";
            document.getElementById("btnStop").style.display = "none";
            document.getElementById("status").innerText = "Status: Perkongsian lokasi dihentikan.";
        }
    </script>
</body>
</html>
"""

# 2. Antaramuka Peta Interaktif + Penjana Pautan WhatsApp untuk Admin
HTML_ADMIN_MAP = """
<!DOCTYPE html>
<html lang="ms">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Peta Pemantauan & WhatsApp</title>
    <link rel="stylesheet" href="https://unpkg.com" />
    <style>
        body { margin: 0; font-family: Arial, sans-serif; display: flex; flex-direction: column; height: 100vh; }
        header { background: #212529; color: white; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }
        .wa-bar { background: #f8f9fa; padding: 10px 20px; border-bottom: 1px solid #ddd; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
        .wa-bar input { padding: 8px 12px; border: 1px solid #ccc; border-radius: 5px; font-size: 14px; }
        .btn-wa { background: #25D366; color: white; border: none; padding: 9px 15px; border-radius: 5px; font-weight: bold; cursor: pointer; font-size: 14px; }
        .btn-copy { background: #6c757d; color: white; border: none; padding: 9px 15px; border-radius: 5px; cursor: pointer; font-size: 14px; }
        #map { flex-grow: 1; width: 100%; }
        .badge { background: #28a745; padding: 4px 10px; border-radius: 12px; font-size: 12px; }
    </style>
</head>
<body>
    <header>
        <div><strong>Dashboard Penghantaran (Supabase Cloud)</strong></div>
        <div class="badge" id="info-aktif">Memuatkan data...</div>
    </header>

    <div class="wa-bar">
        <input type="text" id="inputOrder" placeholder="ID Pesanan (cth: ORD101)" required>
        <input type="text" id="inputPhone" placeholder="No. WhatsApp (cth: 0123456789)">
        <button class="btn-wa" onclick="hantarWhatsApp()">Hantar Link Tracking ke WhatsApp</button>
        <button class="btn-copy" onclick="salinPautan()">Salin Link</button>
    </div>

    <div id="map"></div>

    <script src="https://unpkg.com"></script>
    <script>
        function janaPautan() {
            const orderId = document.getElementById('inputOrder').value.trim();
            if (!orderId) {
                alert("Sila masukkan ID Pesanan terlebih dahulu.");
                return null;
            }
            return `${window.location.origin}/track/${encodeURIComponent(orderId)}`;
        }

        function hantarWhatsApp() {
            const link = janaPautan();
            if (!link) return;
            let phone = document.getElementById('inputPhone').value.replace(/[^0-9]/g, '');
            if (phone.startsWith('0')) phone = '6' + phone;
            const orderId = document.getElementById('inputOrder').value.trim();
            const mesej = `Salam, sila tekan pautan di bawah dan benarkan akses lokasi untuk penghantaran *#${orderId}*:\n\n${link}`;
            const waUrl = phone ? `https://wa.me{phone}?text=${encodeURIComponent(mesej)}` : `https://wa.me{encodeURIComponent(mesej)}`;
            window.open(waUrl, '_blank');
        }

        function salinPautan() {
            const link = janaPautan();
            if (!link) return;
            navigator.clipboard.writeText(link).then(() => alert("Pautan disalin:\n" + link));
        }

        const map = L.map('map').setView([4.5975, 101.0901], 11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map);

        let markers = {};
        let pertamaKali = true;

        function kemaskiniPeta() {
            fetch('/api/semua-lokasi')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('info-aktif').innerText = `Aktif: ${data.length} penghantaran`;
                    let bounds = [];

                    data.forEach(item => {
                        const latLng = [item.lat, item.lon];
                        bounds.push(latLng);
                        const popupInfo = `
                            <strong>Order: #${item.order_id}</strong><br>
                            Masa: ${item.kemaskini_terakhir}<br>
                            Ketepatan: ±${item.accuracy}m<br>
                            <a href="${item.google_maps}" target="_blank">Buka di Google Maps</a>
                        `;

                        if (markers[item.order_id]) {
                            markers[item.order_id].setLatLng(latLng).setPopupContent(popupInfo);
                        } else {
                            markers[item.order_id] = L.marker(latLng).addTo(map).bindPopup(popupInfo);
                        }
                    });

                    if (pertamaKali && bounds.length > 0) {
                        map.fitBounds(bounds, { maxZoom: 15 });
                        pertamaKali = false;
                    }
                });
        }

        kemaskiniPeta();
        setInterval(kemaskiniPeta, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return "Sistem Penjejakan Penghantaran Aktif. Layari /admin/peta untuk dashboard."

@app.route('/track/<order_id>')
def halaman_track(order_id):
    return render_template_string(HTML_LIVE_TRACK, order_id=order_id)

@app.route('/admin/peta')
def halaman_peta():
    return render_template_string(HTML_ADMIN_MAP)

@app.route('/api/update-lokasi', methods=['POST'])
def terima_lokasi():
    data = request.json
    order_id = data.get('order_id')
    lat = data.get('lat')
    lon = data.get('lon')
    accuracy = round(data.get('accuracy', 0), 2)
    maps_url = f"https://google.com{lat},{lon}"
    masa = datetime.now(MY_TZ).strftime("%Y-%m-%d %H:%M:%S")

    rekod = {
        "order_id": order_id,
        "lat": lat,
        "lon": lon,
        "accuracy": accuracy,
        "google_maps": maps_url,
        "kemaskini_terakhir": masa
    }

    # Simpan atau kemas kini rekod terus ke Supabase Cloud
    supabase.table("lokasi_log").upsert(rekod).execute()
    return jsonify({"status": "berjaya"})

@app.route('/api/semua-lokasi')
    def api_semua_lokasi():
    response = supabase.table("lokasi_log").select("*").order("kemaskini_terakhir", desc=True).execute()
    return jsonify(response.data)
    if name == 'main':
    app.run(host='0.0.0.0', port=5000)

