import requests

# Login como admin
r = requests.post("http://localhost:8000/auth/login", json={"username": "admin", "password": "admin123"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# Listar OS
r2 = requests.get("http://localhost:8000/ordens", headers=headers)
data = r2.json()
print(f"Total OS: {len(data)}")
for os_item in data[:3]:
    print(f"  {os_item['numero']} - {os_item['razao_social']} - {os_item['status']}")

# Alertas
r3 = requests.get("http://localhost:8000/alertas", headers=headers)
alertas = r3.json()
print(f"\nTotal alertas: {len(alertas)}")
