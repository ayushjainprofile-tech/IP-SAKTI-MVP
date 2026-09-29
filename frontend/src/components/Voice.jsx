/*
 * Voice layer for IP-SAKTI: speech-to-text for text inputs and optional
 * read-aloud for generated answers. Browser Web Speech API only: no audio
 * is recorded, stored or sent to the IP-SAKTI backend. The transcript is
 * written into the field as plain text and goes through the same
 * validation as typed input (the backend resolves "नीम" → neem, and rejects
 * "latent" the same way whether it was typed or spoken).
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const SpeechRecognitionImpl =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

const synth = typeof window !== "undefined" ? window.speechSynthesis : null;

// App language → BCP-47 recognition locale. en-IN copes with Hinglish and
// Indian names; hi-IN returns Devanagari for Hindi / mixed speech.
const LOCALES = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

const TEXT = {
  en: {
    speak: "Speak", stop: "Stop listening", listening: "Listening…", processing: "Processing…",
    denied: "Microphone permission is required for voice input. You can continue typing manually.",
    unsupported: "Voice input isn't supported in this browser. Please use typing instead.",
    noSpeech: "No speech was detected. Please try again.",
    failed: "Voice input failed. Please try again or type instead.",
    listen: "Listen", pause: "Pause", resume: "Resume", stopAudio: "Stop",
  },
  hi: {
    speak: "बोलें", stop: "सुनना बंद करें", listening: "सुन रहा है…", processing: "प्रोसेस हो रहा है…",
    denied: "आवाज़ से लिखने के लिए माइक्रोफ़ोन की अनुमति चाहिए। आप टाइप करना जारी रख सकते हैं।",
    unsupported: "इस ब्राउज़र में आवाज़ से लिखना समर्थित नहीं है। कृपया टाइप करें।",
    noSpeech: "कोई आवाज़ नहीं सुनाई दी। कृपया फिर से प्रयास करें।",
    failed: "आवाज़ इनपुट विफल रहा। कृपया फिर से प्रयास करें या टाइप करें।",
    listen: "सुनें", pause: "रोकें", resume: "जारी रखें", stopAudio: "बंद करें",
  },
  mr: {
    speak: "बोला", stop: "ऐकणे थांबवा", listening: "ऐकत आहे…", processing: "प्रक्रिया सुरू आहे…",
    denied: "आवाजाने लिहिण्यासाठी मायक्रोफोनची परवानगी आवश्यक आहे. तुम्ही टाइप करणे सुरू ठेवू शकता.",
    unsupported: "या ब्राउझरमध्ये आवाजाने लिहिणे समर्थित नाही. कृपया टाइप करा.",
    noSpeech: "कोणताही आवाज ऐकू आला नाही. कृपया पुन्हा प्रयत्न करा.",
    failed: "आवाज इनपुट अयशस्वी झाले. कृपया पुन्हा प्रयत्न करा किंवा टाइप करा.",
    listen: "ऐका", pause: "थांबवा", resume: "सुरू ठेवा", stopAudio: "बंद करा",
  },
};
const t = (language) => TEXT[language] || TEXT.en;

/* ---------------- one global recognition session ---------------- */

let session = null; // { owner, recognition }
let permissionDenied = false;
const listeners = new Set();
const notify = () => listeners.forEach((fn) => fn());
const subscribe = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};
const currentOwner = () => (session ? session.owner : null);

function stopSession() {
  if (!session) return;
  const { recognition } = session;
  session = null;
  try { recognition.abort(); } catch { /* already stopped */ }
  notify();
}

/**
 * useVoiceInput — speech-to-text bound to one target field.
 *   onTranscript(text): called with the final transcript for this field.
 * Returns { supported, listening, processing, interim, error, start, stop, toggle }.
 * Starting one field stops any other field that is listening.
 */
export function useVoiceInput({ language = "en", onTranscript }) {
  const idRef = useRef(Symbol("voice-field"));
  const owner = useSyncExternalStore(subscribe, currentOwner, currentOwner);
  const listening = owner === idRef.current;
  const [processing, setProcessing] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState("");
  const callbackRef = useRef(onTranscript);
  callbackRef.current = onTranscript;

  useEffect(() => () => {
    if (currentOwner() === idRef.current) stopSession();
  }, []);

  function start() {
    const txt = t(language);
    if (!SpeechRecognitionImpl) { setError(txt.unsupported); return; }
    if (permissionDenied) { setError(txt.denied); return; }
    stopSession(); // only one session at a time

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = LOCALES[language] || "en-IN";
    recognition.interimResults = true;
    recognition.continuous = false; // stops by itself when speech ends
    recognition.maxAlternatives = 1;

    let finalText = "";
    const me = idRef.current;
    recognition.onresult = (event) => {
      let partial = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += piece;
        else partial += piece;
      }
      setInterim(partial);
      if (finalText) setProcessing(true);
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        permissionDenied = true; // don't ask again this page load
        setError(txt.denied);
      } else if (event.error === "no-speech") {
        setError(txt.noSpeech);
      } else if (event.error !== "aborted") {
        setError(txt.failed);
      }
    };
    recognition.onend = () => {
      setInterim("");
      setProcessing(false);
      const text = finalText.trim();
      if (text) callbackRef.current?.(text);
      if (session && session.owner === me) { session = null; notify(); }
    };

    setError("");
    setInterim("");
    session = { owner: me, recognition };
    notify();
    try {
      recognition.start();
    } catch {
      session = null;
      notify();
      setError(txt.failed);
    }
  }

  function stop() {
    if (!listening || !session) return;
    try { session.recognition.stop(); } catch { stopSession(); } // stop() keeps the final result
  }

  return {
    supported: Boolean(SpeechRecognitionImpl),
    listening, processing, interim, error,
    start, stop, toggle: () => (listening ? stop() : start()),
  };
}

/** Outline microphone (Material "mic" glyph); takes the button's colour. */
function MicIcon() {
  return (
    <svg className="voice-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"
      />
    </svg>
  );
}

/** Small mic button; keeps the look of the surrounding field. */
export function VoiceInputButton({ voice, language = "en", className = "" }) {
  const txt = t(language);
  const label = voice.listening ? "Stop voice input" : "Voice input";
  return (
    <button
      type="button"
      className={`voice-btn ${voice.listening ? "listening" : ""} ${voice.processing ? "processing" : ""} ${className}`}
      onClick={voice.toggle}
      aria-label={label}
      aria-pressed={voice.listening}
      title={voice.listening ? txt.stop : txt.speak}
    >
      {voice.processing ? <span className="voice-spinner" aria-hidden="true" /> : <MicIcon />}
    </button>
  );
}

function VoiceStatus({ voice, language }) {
  const txt = t(language);
  if (voice.error) return <div className="voice-status voice-error" role="alert">{voice.error}</div>;
  if (voice.processing) return <div className="voice-status" aria-live="polite">{txt.processing}</div>;
  if (voice.listening) {
    return (
      <div className="voice-status" aria-live="polite">
        {txt.listening}{voice.interim ? ` “${voice.interim}”` : ""}
      </div>
    );
  }
  return null;
}

/**
 * VoiceField — an <input> or <textarea> with a mic. Spoken text is appended
 * to the current value of THIS field (with `separator` between entries) and
 * never submitted automatically.
 */
export function VoiceField({
  as = "input", value, onValueChange, language = "en", separator = " ", ...props
}) {
  const voice = useVoiceInput({
    language,
    onTranscript: (text) => {
      const current = String(value || "").trim();
      onValueChange(current ? `${current}${separator}${text}` : text);
    },
  });
  const Tag = as;
  return (
    <div className="voice-field-wrap">
      <div className={`voice-field ${as === "textarea" ? "is-textarea" : ""}`}>
        <Tag {...props} value={value} onChange={(e) => onValueChange(e.target.value)} />
        <VoiceInputButton voice={voice} language={language} />
      </div>
      <VoiceStatus voice={voice} language={language} />
    </div>
  );
}

/* ---------------- read aloud ---------------- */

let speakingId = null;
const speechListeners = new Set();
const speechSubscribe = (fn) => { speechListeners.add(fn); return () => speechListeners.delete(fn); };
const setSpeaking = (id) => { speakingId = id; speechListeners.forEach((fn) => fn()); };
const getSpeaking = () => speakingId;

function pickVoice(locale) {
  const voices = synth?.getVoices?.() || [];
  const base = locale.split("-")[0];
  return (
    voices.find((v) => v.lang === locale) ||
    voices.find((v) => v.lang?.startsWith(base)) ||
    null
  );
}

function detectLocale(text, language) {
  if (/[ऀ-ॿ]/.test(text)) return language === "mr" ? "mr-IN" : "hi-IN";
  return LOCALES[language] || "en-IN";
}

/**
 * SpeakButton — optional read-aloud for generated content (never automatic).
 * States: 🔊 Listen → ⏸ Pause / ▶ Resume, ⏹ Stop.
 */
export function SpeakButton({ text, language = "en", className = "" }) {
  const idRef = useRef(Symbol("speak"));
  const active = useSyncExternalStore(speechSubscribe, getSpeaking, getSpeaking) === idRef.current;
  const [paused, setPaused] = useState(false);
  const txt = t(language);

  useEffect(() => () => {
    if (getSpeaking() === idRef.current) { synth?.cancel(); setSpeaking(null); }
  }, []);

  if (!synth || !String(text || "").trim()) return null;

  function play() {
    synth.cancel(); // one answer at a time
    const clean = String(text).replace(/[*_#`>]/g, " ").replace(/\s+/g, " ").trim();
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = detectLocale(clean, language);
    const voice = pickVoice(utterance.lang);
    if (voice) utterance.voice = voice;
    const me = idRef.current;
    utterance.onend = utterance.onerror = () => {
      if (getSpeaking() === me) { setSpeaking(null); setPaused(false); }
    };
    setPaused(false);
    setSpeaking(me);
    synth.speak(utterance);
  }
  function pauseResume() {
    if (paused) { synth.resume(); setPaused(false); } else { synth.pause(); setPaused(true); }
  }
  function stop() { synth.cancel(); setSpeaking(null); setPaused(false); }

  if (!active) {
    return (
      <button type="button" className={`speak-btn ${className}`} onClick={play} aria-label="Read aloud" title={txt.listen}>
        🔊 {txt.listen}
      </button>
    );
  }
  return (
    <span className={`speak-controls ${className}`}>
      <button type="button" className="speak-btn" onClick={pauseResume} aria-label={paused ? "Resume" : "Pause"}>
        {paused ? `▶ ${txt.resume}` : `⏸ ${txt.pause}`}
      </button>
      <button type="button" className="speak-btn" onClick={stop} aria-label="Stop reading">
        ⏹ {txt.stopAudio}
      </button>
    </span>
  );
}
