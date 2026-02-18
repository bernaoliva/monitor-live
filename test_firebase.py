import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
fs = firestore.client(database_id="default")
fs.collection("lives").document("teste").set({"status": "ok", "msg": "conexao funcionando"})
print("Firestore conectado com sucesso!")
