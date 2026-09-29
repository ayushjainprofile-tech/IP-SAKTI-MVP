import { useState } from "react";
import { Routes, Route } from "react-router-dom";
import LandingPage from "./LandingPage";
import Navbar from "./components/Navbar";
import { VoiceField, SpeakButton } from "./components/Voice";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";

import heroBgVideo from "./white-sheet-bg.mp4";

const API_ENDPOINTS = [
  import.meta.env.VITE_API_URL,
  "http://localhost:8001",
  "http://127.0.0.1:8001",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
].filter(Boolean);

/* Render free tier sleeps when idle; cold start can take ~50s */
function requestTimeout(host, localMs) {
  return /localhost|127\.0\.0\.1/.test(host) ? localMs : 90000;
}

/* Wake the hosted backend as soon as the app loads */
if (import.meta.env.VITE_API_URL) {
  fetch(`${import.meta.env.VITE_API_URL}/api/health`).catch(() => {});
}

/* Safely convert any value to a renderable string */
function toStr(val) {
  if (val === null || val === undefined) return "";
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  // For objects/arrays, stringify them
  try { return JSON.stringify(val); } catch { return String(val); }
}

/* Domain bar status comes only from backend routing + validation. */
function getDomainMetrics(result, domainCode) {
  const domains = result.domains || [];
  const supported = result.validation?.supported_domains || [];
  const confScore = result.confidence?.score ?? 0;

  if (result.validation?.status === "OUT_OF_SCOPE") {
    return { width: "0%", label: "Out of scope", color: "#9f1239" };
  }
  if (!domains.includes(domainCode)) {
    return { width: "0%", label: "Not routed", color: "#6b7280" };
  }
  if (supported.includes(domainCode)) {
    return { width: `${Math.round(confScore * 100)}%`, label: "Evidence found", color: "#3F6844" };
  }
  return { width: "0%", label: "No evidence", color: "#8A6421" };
}

function Dashboard() {
  const [language, setLanguage] = useState("en"); // "en", "hi", "mr"
  const [form, setForm] = useState({
    product_name: "Ashwa Joint Relief",
    ingredients: "Ashwagandha, Turmeric",
    purpose: "Joint pain",
    product_type: "Ayurvedic formulation",
    jurisdiction: "India",
    based_on_traditional_knowledge: "Not sure",
  });

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Chatbot State
  const [chatMessages, setChatMessages] = useState([
    {
      role: "assistant",
      content: language === "hi"
        ? "नमस्ते! मैं IP-SAKTI AI हूँ। आप मुझसे IP, पारंपरिक ज्ञान (TK), ABS और पेटेंट नियमों के बारे में प्रश्न पूछ सकते हैं।"
        : language === "mr"
        ? "नमस्कार! मी IP-SAKTI AI आहे. तुम्ही मला IP, पारंपारिक ज्ञान (TK), ABS आणि पेटंट नियमांबद्दल प्रश्न विचारू शकता."
        : "Hello! I am IP-SAKTI AI. Ask me any questions about IP, Traditional Knowledge, ABS, Ayurveda, or patent regulations.",
      trace: ["System initialized", "Awaiting query"],
      sources: []
    }
  ]);
  const [chatQuery, setChatQuery] = useState("");
  // "expert": detailed legal wording; "friendly": simple, conversational.
  const [chatMode, setChatMode] = useState("expert");
  const [chatLoading, setChatLoading] = useState(false);
  const [expandedTrace, setExpandedTrace] = useState({});

  function update(key, value) {
    setForm((old) => ({ ...old, [key]: value }));
  }

  async function analyze(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    const payload = {
      ...form,
      language: language,
      ingredients: form.ingredients
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    };

    let data = null;
    for (const host of API_ENDPOINTS) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), requestTimeout(host, 2000));
        const response = await fetch(`${host}/api/analyze`, {
          method: "POST",
          headers: { 
            "Content-Type": "application/json",
            "Bypass-Tunnel-Reminder": "true"
          },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (response.ok) {
          data = await response.json();
          break;
        }
        if (response.status === 422) {
          // Backend understood the request but rejected the input.
          const body = await response.json().catch(() => ({}));
          setError(toStr(body.detail?.message || "Please check the product details and try again."));
          setLoading(false);
          return;
        }
      } catch (err) {
        // Fallback to next endpoint or instant smart analysis
      }
    }

    if (!data) {
      // Never show placeholder scores: confidence must come from the
      // backend's Product Context Engine.
      setError("Could not reach the analysis backend. Please try again in a minute (the server may be waking up).");
      setLoading(false);
      return;
    }

    setResult(data);
    setLoading(false);
  }

  async function handleChatSubmit(e) {
    e.preventDefault();
    const query = chatQuery.trim();
    if (!query || chatLoading) return;

    const userMsg = { role: "user", content: query };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatQuery("");
    setChatLoading(true);

    let chatData = null;
    for (const host of API_ENDPOINTS) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), requestTimeout(host, 3000));
        const response = await fetch(`${host}/api/agent/chat`, {
          method: "POST",
          headers: { 
            "Content-Type": "application/json",
            "Bypass-Tunnel-Reminder": "true"
          },
          body: JSON.stringify({
            query: query,
            jurisdiction: form.jurisdiction || "India",
            language: language,
            mode: chatMode
          }),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (response.ok) {
          chatData = await response.json();
          break;
        }
      } catch (err) {
        // Continue to next endpoint
      }
    }

    if (!chatData) {
      // Never invent an answer: every reply must come from the backend.
      chatData = {
        answer: language === "hi"
          ? "सर्वर से संपर्क नहीं हो सका। कृपया एक मिनट बाद फिर से प्रयास करें।"
          : language === "mr"
          ? "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया एका मिनिटानंतर पुन्हा प्रयत्न करा."
          : "Could not reach the IP-SAKTI server. Please try again in a minute.",
      };
    }

    const botMsg = {
      role: "assistant",
      content: chatData.answer || chatData.response || "No response received.",
      trace: chatData.agent_trace || chatData.trace || [],
      sources: chatData.sources || chatData.citations || [],
      mode: chatData.mode,
      confidence: typeof chatData.confidence === "object" ? chatData.confidence?.level || "" : chatData.confidence
    };

    setChatMessages((prev) => [...prev, botMsg]);
    setChatLoading(false);
  }

  function toggleTrace(idx) {
    setExpandedTrace((prev) => ({ ...prev, [idx]: !prev[idx] }));
  }

  /* Extract a human-readable reasoning string from the backend response */
  function getReasoningText(res) {
    if (res.llm_reasoning) {
      if (typeof res.llm_reasoning === "string") return res.llm_reasoning;
      if (res.llm_reasoning.answer) return res.llm_reasoning.answer;
      if (res.llm_reasoning.message) return res.llm_reasoning.message;
    }
    if (res.reasoning) {
      if (typeof res.reasoning === "string") return res.reasoning;
      if (res.reasoning.answer) return res.reasoning.answer;
      if (res.reasoning.summary) return res.reasoning.summary;
    }
    return "No reasoning available.";
  }

  /* Extract validation status */
  function getValidationStatus(res) {
    if (!res.validation) return "UNKNOWN";
    if (res.validation.status) return res.validation.status;
    if (res.validation.is_supported) return "SUPPORTED";
    return "UNSUPPORTED";
  }

  /* Extract validation message */
  function getValidationMessage(res) {
    if (!res.validation) return "";
    if (res.validation.message) return toStr(res.validation.message);
    if (res.validation.summary) return toStr(res.validation.summary);
    const parts = [];
    if (res.validation.supported_domains?.length) {
      parts.push("Supported: " + res.validation.supported_domains.join(", "));
    }
    if (res.validation.unsupported_domains?.length) {
      parts.push("Unsupported: " + res.validation.unsupported_domains.join(", "));
    }
    return parts.join(" · ") || toStr(res.validation.status);
  }

  return (
    <div className="app app-dashboard-page">
      <div className="dashboard-video-bg">
        <video
          className="bg-video"
          src={heroBgVideo}
          autoPlay
          loop
          muted
          playsInline
        />
        <div className="dashboard-video-overlay" />
      </div>

      <header className="hero">
        <div>
          <div className="eyebrow">CODEHUNTERS HACKATHON MVP</div>
          <h1>IP-SAKTI</h1>
          <p>
            {language === "hi"
              ? "IP, पारंपरिक ज्ञान और ABS मूल्यांकन के लिए साक्ष्य-आधारित सहायक।"
              : language === "mr"
              ? "IP, पारंपारिक ज्ञान आणि ABS मूल्यमापनासाठी पुरावा-आधारित सहाय्यक."
              : "Evidence-first assistant for preliminary IP, Traditional Knowledge and ABS assessment."}
          </p>
        </div>
        <div className="hero-right-group">
          <div className="language-selector-badge">
            <span className="lang-icon">🌐</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="lang-select-input"
            >
              <option value="en">English</option>
              <option value="hi">हिंदी (Hindi)</option>
              <option value="mr">मराठी (Marathi)</option>
            </select>
          </div>
          <div className="architecture-pill">
            Intake → Classify → Route → Retrieve → Verify → Act
          </div>
        </div>
      </header>

      <main className="layout">
        <section className="card">
          <div className="card-header-row">
            <div className="card-eyebrow">
              {language === "hi" ? "विश्लेषण प्रश्न" : language === "mr" ? "मूल्यमापन प्रश्न" : "ANALYSIS QUERY"}
            </div>
            <div className="card-number">01</div>
          </div>
          <h2>{language === "hi" ? "1. उत्पाद की जानकारी" : language === "mr" ? "1. उत्पादनाची माहिती" : "1. Product Intake"}</h2>
          <p className="muted">
            {language === "hi"
              ? "उपयोगकर्ता द्वारा प्रदान की गई जानकारी से प्रारंभ करें।"
              : language === "mr"
              ? "वापरकर्त्याने दिलेल्या माहितीपासून सुरुवात करा."
              : "Start with what the user actually knows. The system should not assume missing facts."}
          </p>

          <form onSubmit={analyze}>
            <label>{language === "hi" ? "उत्पाद का नाम" : language === "mr" ? "उत्पादनाचे नाव" : "Product name"}</label>
            <VoiceField
              value={form.product_name}
              onValueChange={(v) => update("product_name", v)}
              language={language}
              required
            />

            <label>{language === "hi" ? "सामग्री / घटक" : language === "mr" ? "घटक" : "Ingredients / components"}</label>
            <VoiceField
              value={form.ingredients}
              onValueChange={(v) => update("ingredients", v)}
              language={language}
              separator=", "
              placeholder="Comma separated"
            />

            <label>{language === "hi" ? "उद्देश्य / उपयोग" : language === "mr" ? "उद्देश / वापर" : "Intended use"}</label>
            <VoiceField
              as="textarea"
              value={form.purpose}
              onValueChange={(v) => update("purpose", v)}
              language={language}
            />

            <label>{language === "hi" ? "उत्पाद का प्रकार" : language === "mr" ? "उत्पादनाचा प्रकार" : "Product type"}</label>
            <select
              value={form.product_type}
              onChange={(e) => update("product_type", e.target.value)}
            >
              <option>Ayurvedic formulation</option>
              <option>Herbal product</option>
              <option>Food</option>
              <option>Cosmetic</option>
              <option>Other</option>
            </select>

            <label>{language === "hi" ? "क्षेत्रीय क्षेत्राधिकार" : language === "mr" ? "क्षेत्राधिकार" : "Jurisdiction"}</label>
            <select
              value={form.jurisdiction}
              onChange={(e) => update("jurisdiction", e.target.value)}
            >
              <option>India</option>
            </select>

            <label>{language === "hi" ? "क्या यह पारंपरिक ज्ञान पर आधारित है?" : language === "mr" ? "हे पारंपारिक ज्ञानावर आधारित आहे का?" : "Based on traditional knowledge?"}</label>
            <select
              value={form.based_on_traditional_knowledge}
              onChange={(e) =>
                update("based_on_traditional_knowledge", e.target.value)
              }
            >
              <option>Not sure</option>
              <option>Yes</option>
              <option>No</option>
            </select>

            <button disabled={loading}>
              {loading
                ? (language === "hi" ? "विश्लेषण जारी है..." : language === "mr" ? "विश्लेषण सुरू आहे..." : "Analyzing...")
                : (language === "hi" ? "उत्पाद का विश्लेषण करें →" : language === "mr" ? "उत्पादनाचे विश्लेषण करा →" : "ANALYZE PRODUCT →")}
            </button>
          </form>

          {error && <div className="error">{error}</div>}
        </section>

        <section className="results">
          {!result && (
            <div className="empty card">
              <div className="card-header-row" style={{ width: '100%' }}>
                <div className="card-eyebrow">FIELD JOURNAL</div>
                <div className="card-number">02</div>
              </div>
              <div className="big-icon">🌿</div>
              <h2>{language === "hi" ? "आपका विश्लेषण यहाँ दिखाई देगा" : language === "mr" ? "तुमचे विश्लेषण येथे दिसेल" : "Your analysis will appear here"}</h2>
              <p className="muted">
                The prototype will classify the product, route it to IP/TK/ABS,
                retrieve evidence, validate the response and create an action
                plan.
              </p>
            </div>
          )}

          {result && (
            <>
              {/* CLASSIFICATION */}
              <div className="card">
                <div className="card-header-row">
                  <div className="card-eyebrow">PRELIMINARY CLASSIFICATION</div>
                  <div className="card-number">02</div>
                </div>
                <div className="result-header">
                  <div>
                    <h2>{toStr(result.classification?.label || result.classification?.product_type || "Unknown")}</h2>
                  </div>
                  <div className="status">{getValidationStatus(result)}</div>
                </div>
                <ul>
                  {result.classification?.reasons
                    ? result.classification.reasons.map((r, i) => (
                        <li key={i}>{toStr(r)}</li>
                      ))
                    : (
                      <>
                        {result.classification?.classification_note && (
                          <li>{toStr(result.classification.classification_note)}</li>
                        )}
                        {result.classification?.traditional_knowledge_status && (
                          <li>TK Status: {toStr(result.classification.traditional_knowledge_status)}</li>
                        )}
                        {result.classification?.jurisdiction && (
                          <li>Jurisdiction: {toStr(result.classification.jurisdiction)}</li>
                        )}
                      </>
                    )
                  }
                </ul>
              </div>

              {/* DOMAIN ROUTER + CONFIDENCE */}
              <div className="grid">
                <div className="card">
                  <div className="card-header-row">
                    <div className="card-eyebrow">DOMAIN STATUS</div>
                    <div className="card-number">03</div>
                  </div>
                  <h3>Domain Router</h3>
                  <div className="chips">
                    {(result.domains || []).map((d) => (
                      <span className="chip" key={d}>{toStr(d)}</span>
                    ))}
                  </div>

                  <div className="domain-bar-group">
                    {(() => {
                      const tk = getDomainMetrics(result, "TK");
                      const abs = getDomainMetrics(result, "ABS");
                      const ip = getDomainMetrics(result, "IP");
                      return (
                        <>
                          <div className="domain-bar-item">
                            <div className="domain-bar-header">
                              <span>Traditional Knowledge (TK)</span>
                              <span className="tag" style={{ background: tk.color, color: "#fff" }}>{tk.label}</span>
                            </div>
                            <div className="domain-progress-track">
                              <div className="domain-progress-fill" style={{ width: tk.width, background: tk.color }}></div>
                            </div>
                          </div>

                          <div className="domain-bar-item">
                            <div className="domain-bar-header">
                              <span>Access & Benefit Sharing (ABS)</span>
                              <span className="tag" style={{ background: abs.color, color: "#fff" }}>{abs.label}</span>
                            </div>
                            <div className="domain-progress-track">
                              <div className="domain-progress-fill" style={{ width: abs.width, background: abs.color }}></div>
                            </div>
                          </div>

                          <div className="domain-bar-item">
                            <div className="domain-bar-header">
                              <span>Intellectual Property (IP)</span>
                              <span className="tag" style={{ background: ip.color, color: "#fff" }}>{ip.label}</span>
                            </div>
                            <div className="domain-progress-track">
                              <div className="domain-progress-fill" style={{ width: ip.width, background: ip.color }}></div>
                            </div>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header-row">
                    <div className="card-eyebrow">CONFIDENCE SCORE</div>
                    <div className="card-number">04</div>
                  </div>
                  <h3>Confidence</h3>
                  <div className="confidence">
                    {Math.round((result.confidence?.score || 0) * 100)}%
                  </div>
                  <strong>{toStr(result.confidence?.level || result.confidence?.label || "")}</strong>
                  {(result.product_context_engine?.context?.relevance_reasons || []).length > 0 && (
                    <p><strong>Product Context Engine:</strong> {result.product_context_engine.context.relevance_reasons.map(toStr).join(" ")}</p>
                  )}
                  <p className="muted">{toStr(result.confidence?.warning || result.confidence?.meaning || "")}</p>
                  <SpeakButton
                    text={[
                      `${Math.round((result.confidence?.score || 0) * 100)}%`,
                      toStr(result.confidence?.level || ""),
                      ...(result.product_context_engine?.context?.relevance_reasons || []).map(toStr),
                    ].join(". ")}
                    language={language}
                  />
                </div>
              </div>

              {/* EVIDENCE */}
              <div className="card">
                <div className="card-header-row">
                  <div className="card-eyebrow">EVIDENCE SOURCES</div>
                  <div className="card-number">05</div>
                </div>
                <h3>Retrieved Evidence</h3>
                {(!result.evidence || result.evidence.length === 0) ? (
                  <p className="muted">No evidence was retrieved.</p>
                ) : (
                  result.evidence.map((e, idx) => (
                    <article className="evidence" key={e.id || idx}>
                      <div className="evidence-top">
                        <strong>{toStr(e.title || e.source || e.id || `Evidence ${idx + 1}`)}</strong>
                        <span>{typeof e.score === "number" ? Math.round(e.score) : toStr(e.score)}</span>
                      </div>
                      <p>{toStr(e.text || "")}</p>
                      <small>
                        {toStr(e.source || "")} · {toStr(e.domain || "")}
                        {e.source_url && (
                          <>
                            {" · "}
                            <a href={e.source_url} target="_blank" rel="noreferrer">
                              Official source
                            </a>
                          </>
                        )}
                      </small>
                    </article>
                  ))
                )}
              </div>

              {/* VALIDATION */}
              {getValidationMessage(result) && (
                <div className="card">
                  <div className="card-header-row">
                    <div className="card-eyebrow">SOURCE VALIDATION</div>
                    <div className="card-number">06</div>
                  </div>
                  <h3>Verification Status</h3>
                  <p className="muted">{getValidationMessage(result)}</p>
                </div>
              )}

              {/* ACTION PLAN */}
              <div className="card">
                <div className="card-header-row">
                  <div className="card-eyebrow">RECOMMENDED ACTION PLAN</div>
                  <div className="card-number">07</div>
                </div>
                <h3>Action Plan</h3>
                <SpeakButton text={(result.action_plan || []).map(toStr).join(". ")} language={language} />
                <ol>
                  {(result.action_plan || []).map((step, i) => (
                    <li key={i}>{toStr(step)}</li>
                  ))}
                </ol>
              </div>
            </>
          )}

          {/* 🤖 ASK IP-SAKTI AI CHATBOT SECTION (replicated from streamlit_app.py) */}
          <div className="card chatbot-card">
            <div className="card-header-row">
              <div className="card-eyebrow">
                {language === "hi" ? "एजेंटिक एआई चैट" : language === "mr" ? "एजंटिक एआय चॅट" : "AGENTIC AI ASSISTANT"}
              </div>
              <div className="card-number">🤖</div>
            </div>
            <h2>{language === "hi" ? "🤖 IP-SAKTI AI से पूछें" : language === "mr" ? "🤖 IP-SAKTI AI ला विचारा" : "🤖 Ask IP-SAKTI AI"}</h2>
            <p className="muted">
              {language === "hi"
                ? "आईपी, पारंपरिक ज्ञान, एबीएस, आयुर्वेद और संबंधित कानूनों के बारे में प्रश्न पूछें।"
                : language === "mr"
                ? "आयपी, पारंपारिक ज्ञान, एबीएस, आयुर्वेद आणि संबंधित नियमांबद्दल प्रश्न विचारा."
                : "Ask questions about IP, Traditional Knowledge, ABS, Ayurveda and related regulations."}
            </p>

            <div className="chat-thread">
              {chatMessages.map((msg, idx) => (
                <div key={idx} className={`chat-bubble-container ${msg.role}`}>
                  <div className={`chat-bubble ${msg.role}`}>
                    <div className="chat-sender">
                      {msg.role === "user" ? "👤 You" : msg.mode === "friendly" ? "😊 IP-SAKTI Helper" : "🤖 IP-SAKTI Agent"}
                    </div>
                    <div className="chat-content">{msg.content}</div>
                    {msg.role === "assistant" && idx > 0 && (
                      <SpeakButton text={msg.content} language={language} />
                    )}

                    {/* Agent Execution Trace Expander */}
                    {msg.trace && msg.trace.length > 0 && (
                      <div className="chat-trace-box">
                        <button
                          type="button"
                          className="trace-toggle-btn"
                          onClick={() => toggleTrace(idx)}
                        >
                          {expandedTrace[idx] ? "▼ Hide Agent Execution Trace" : "▶ View Agent Execution Trace"}
                        </button>
                        {expandedTrace[idx] && (
                          <ul className="trace-list">
                            {msg.trace.map((step, sIdx) => (
                              <li key={sIdx}>✓ {toStr(step)}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Sources */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="chat-sources-box">
                        <div className="sources-title">📚 Sources:</div>
                        <ul>
                          {msg.sources.map((s, sIdx) => (
                            <li key={sIdx}>
                              <strong>{s.title || s.source || `Source ${sIdx + 1}`}</strong>
                              {s.url && (
                                <>
                                  {" — "}
                                  <a href={s.url} target="_blank" rel="noreferrer">
                                    [Open Link]
                                  </a>
                                </>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {msg.confidence && (
                      <div className="chat-confidence-tag">
                        🎯 Confidence: {msg.confidence}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="chat-bubble-container assistant">
                  <div className="chat-bubble assistant loading">
                    🤖 IP-SAKTI Agent is researching...
                  </div>
                </div>
              )}
            </div>

            <div className="chat-mode-toggle" role="group" aria-label="Answer style">
              <button
                type="button"
                className={chatMode === "expert" ? "active" : ""}
                onClick={() => setChatMode("expert")}
                disabled={chatLoading}
              >
                {language === "hi" ? "🎓 विशेषज्ञ" : language === "mr" ? "🎓 तज्ज्ञ" : "🎓 Expert"}
              </button>
              <button
                type="button"
                className={chatMode === "friendly" ? "active" : ""}
                onClick={() => setChatMode("friendly")}
                disabled={chatLoading}
              >
                {language === "hi" ? "😊 आसान भाषा" : language === "mr" ? "😊 सोपी भाषा" : "😊 Simple words"}
              </button>
            </div>

            <form onSubmit={handleChatSubmit} className="chat-input-form">
              <VoiceField
                type="text"
                value={chatQuery}
                onValueChange={setChatQuery}
                language={language}
                placeholder={
                  language === "hi"
                    ? "IP-SAKTI AI से पूछें... (उदा. धारा 3(p) क्या है?)"
                    : language === "mr"
                    ? "IP-SAKTI AI ला विचारा..."
                    : "Ask IP-SAKTI AI... (e.g. Is Ashwagandha formulation patentable?)"
                }
                disabled={chatLoading}
              />
              <button type="submit" disabled={chatLoading || !chatQuery.trim()}>
                {chatLoading ? "..." : "SEND →"}
              </button>
            </form>

            {chatMessages.length > 1 && (
              <button
                type="button"
                className="clear-chat-btn"
                onClick={() =>
                  setChatMessages([
                    {
                      role: "assistant",
                      content:
                        language === "hi"
                          ? "चैट रीसेट हो गई है। आप नए प्रश्न पूछ सकते हैं।"
                          : language === "mr"
                          ? "चॅट रीसेट झाले आहे."
                          : "Chat cleared. Ask a new question!",
                      trace: [],
                      sources: []
                    }
                  ])
                }
              >
                🗑️ Clear AI Chat
              </button>
            )}
          </div>

          <div className="disclaimer">
            Prototype only — not legal advice, not a patentability determination, and not a substitute for qualified professional review.
          </div>
        </section>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/about" element={<LandingPage />} />
        <Route path="/features" element={<LandingPage />} />
        <Route path="/contact" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/app" element={<Dashboard />} />
      </Routes>
    </>
  );
}
