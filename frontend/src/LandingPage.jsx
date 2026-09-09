import React from 'react';
import { useNavigate } from 'react-router-dom';
import heroBg from '../landing-page/watermark-removed-Ek_Rishi_Muni_kuchh_Granth_lik.mp4';
import './LandingPage.css';

export default function LandingPage() {
  const navigate = useNavigate();

  const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="landing-container">

      {/* ── HERO ── */}
      <section className="landing-page" id="home">
        <div className="video-container">
          <video autoPlay loop muted playsInline src={heroBg} className="bg-video" />
          <div className="video-overlay"></div>
        </div>

        <div className="landing-content">
          <h1>IP-SAKTI</h1>
        </div>

        <div className="hero-btn-corner">
          <button className="cta-button" onClick={() => navigate('/app')}>
            Launch App
          </button>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="lp-section features-section" id="features">
        <div className="lp-section-inner">
          <span className="lp-tag">CORE CAPABILITIES</span>
          <h2>How IP-SAKTI Works</h2>
          <p className="lp-sub">An end-to-end pipeline from product intake to actionable compliance guidance.</p>

          <div className="features-grid">
            <div className="feat-card">
              <div className="feat-icon">📋</div>
              <h3>1. Product Intake</h3>
              <p>Captures formulation details, ingredients, and traditional origin without assuming missing facts.</p>
            </div>
            <div className="feat-card">
              <div className="feat-icon">🧭</div>
              <h3>2. Multi-Domain Router</h3>
              <p>Auto-classifies and routes queries across IP, Traditional Knowledge (TK), and ABS compliance engines.</p>
            </div>
            <div className="feat-card">
              <div className="feat-icon">🔍</div>
              <h3>3. RAG Evidence Engine</h3>
              <p>Retrieves evidence from TKDL, Patents, and Biological Diversity Act legal corpora.</p>
            </div>
            <div className="feat-card">
              <div className="feat-icon">⚖️</div>
              <h3>4. Actionable Guidance</h3>
              <p>Generates risk scores, claim validation reports, and step-by-step action plans.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── ABOUT ── */}
      <section className="lp-section about-section" id="about">
        <div className="lp-section-inner about-inner">
          <div className="about-text">
            <span className="lp-tag">OUR MISSION</span>
            <h2>Protecting Heritage,<br />Accelerating Innovation</h2>
            <p>
              IP-SAKTI bridges the gap between traditional wisdom and modern intellectual property law.
              By leveraging Retrieval-Augmented Generation (RAG) and automated legal classification,
              we empower researchers, startups, and institutions to navigate complex ABS and TK compliance.
            </p>
            <div className="about-stats">
              <div className="stat">
                <span className="stat-num">TKDL</span>
                <span className="stat-lbl">Integrated Database</span>
              </div>
              <div className="stat">
                <span className="stat-num">3+</span>
                <span className="stat-lbl">IP Domains</span>
              </div>
              <div className="stat">
                <span className="stat-num">RAG</span>
                <span className="stat-lbl">Evidence Grounded</span>
              </div>
            </div>
          </div>
          <div className="about-cta">
            <button className="outline-btn" onClick={() => navigate('/signup')}>Get Started →</button>
          </div>
        </div>
      </section>

      {/* ── CONTACT ── */}
      <section className="lp-section contact-section" id="contact">
        <div className="lp-section-inner contact-inner">
          <span className="lp-tag">GET IN TOUCH</span>
          <h2>Contact Us</h2>
          <p className="lp-sub">Have questions about IP-SAKTI? Reach out to us.</p>

          <form className="contact-form" onSubmit={(e) => { e.preventDefault(); alert('Message sent! We will get back to you soon.'); }}>
            <div className="contact-row">
              <input type="text" placeholder="Your Name" required />
              <input type="email" placeholder="Your Email" required />
            </div>
            <textarea placeholder="Your message..." rows={4} required></textarea>
            <button type="submit" className="cta-button contact-submit">Send Message</button>
          </form>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="footer-brand">
            <strong>IP-SAKTI</strong>
            <span>Evidence-first IP & TK assessment platform.</span>
          </div>
          <div className="footer-links">
            <button onClick={() => scrollTo('home')}>Home</button>
            <button onClick={() => scrollTo('features')}>Features</button>
            <button onClick={() => scrollTo('about')}>About</button>
            <button onClick={() => scrollTo('contact')}>Contact</button>
            <button onClick={() => navigate('/login')}>Login</button>
            <button onClick={() => navigate('/signup')}>Sign Up</button>
          </div>
        </div>
        <div className="footer-bottom">© {new Date().getFullYear()} IP-SAKTI — Built for CodeHunters Hackathon</div>
      </footer>

    </div>
  );
}
