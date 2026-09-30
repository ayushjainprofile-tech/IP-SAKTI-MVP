import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyArsi-GyeS57KRJa_fE_FUB9QatYiWiwTU",
  authDomain: "ip-shakti-mvp.firebaseapp.com",
  projectId: "ip-shakti-mvp",
  storageBucket: "ip-shakti-mvp.firebasestorage.app",
  messagingSenderId: "1035720246524",
  appId: "1:1035720246524:web:e4ad14bf32320d631c8379",
  measurementId: "G-BVYZQ3N2XG"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

export { auth, provider, signInWithPopup };
