import { initializeApp, getApps } from "firebase/app"
import { getFirestore } from "firebase/firestore"

const firebaseConfig = {
  apiKey:            "SUA_FIREBASE_API_KEY",
  authDomain:        "SEU_PROJECT_ID.firebaseapp.com",
  projectId:         "SEU_PROJECT_ID",
  storageBucket:     "SEU_PROJECT_ID.firebasestorage.app",
  messagingSenderId: "SEU_SENDER_ID",
  appId:             "SEU_APP_ID",
}

const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
export const db = getFirestore(app)
