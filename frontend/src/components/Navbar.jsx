import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import './Navbar.css';

export default function Navbar() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const prevScrollY = useRef(0);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;

      if (currentScrollY <= 10) {
        setIsVisible(true);
      } else if (currentScrollY > prevScrollY.current && currentScrollY > 70) {
        // Scrolling down
        setIsVisible(false);
      } else if (currentScrollY < prevScrollY.current) {
        // Scrolling up
        setIsVisible(true);
      }

      prevScrollY.current = currentScrollY;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const closeMenu = () => setIsMobileMenuOpen(false);

  const isActive = (path) => location.pathname === path ? 'active' : '';

  const scrollToSection = (id) => {
    closeMenu();
    if (location.pathname !== '/') {
      navigate('/');
      setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
      }, 200);
    } else {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const navClass = `navbar ${!isVisible && !isMobileMenuOpen ? 'navbar--hidden' : ''}`;

  return (
    <nav className={navClass}>
      <div className="navbar-container">
        {/* Left: Logo */}
        <div className="navbar-logo">
          <Link to="/" onClick={closeMenu}>
            <span className="logo-text">IP-SAKTI</span>
          </Link>
        </div>

        {/* Center: Navigation Links (Desktop) */}
        <div className="navbar-links">
          <Link to="/" className={`nav-link ${isActive('/')}`}>Home</Link>
          <button className="nav-link nav-link-btn" onClick={() => scrollToSection('about')}>About</button>
          <button className="nav-link nav-link-btn" onClick={() => scrollToSection('features')}>Features</button>
          <button className="nav-link nav-link-btn" onClick={() => scrollToSection('contact')}>Contact</button>
        </div>

        {/* Right: Auth Buttons (Desktop) */}
        <div className="navbar-auth">
          <Link to="/login" className="nav-btn btn-login">Login</Link>
          <Link to="/signup" className="nav-btn btn-signup">Sign Up</Link>
        </div>

        {/* Mobile Hamburger Icon */}
        <div className="mobile-menu-icon" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X size={28} /> : <Menu size={28} />}
        </div>
      </div>

      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div className="mobile-menu">
          <div className="mobile-links">
            <Link to="/" className={`mobile-link ${isActive('/')}`} onClick={closeMenu}>Home</Link>
            <button className="mobile-link mobile-link-btn" onClick={() => scrollToSection('about')}>About</button>
            <button className="mobile-link mobile-link-btn" onClick={() => scrollToSection('features')}>Features</button>
            <button className="mobile-link mobile-link-btn" onClick={() => scrollToSection('contact')}>Contact</button>

            <div className="mobile-auth-divider"></div>

            <Link to="/login" className="mobile-btn btn-login" onClick={closeMenu}>Login</Link>
            <Link to="/signup" className="mobile-btn btn-signup" onClick={closeMenu}>Sign Up</Link>
          </div>
        </div>
      )}
    </nav>
  );
}
